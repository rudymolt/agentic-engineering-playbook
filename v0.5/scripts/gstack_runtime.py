"""Build pinned gstack into an off-discovery store; never activate host skills."""
from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import urllib.request
import uuid
import zipfile

import gstack_package as package
import upstream_bundle as bundle

POLICY = Path('bundles/gstack/runtime.json')
BUILD_REVISION = 3
BINARIES = (
    ('browse/src/cli.ts', 'browse/dist/browse'),
    ('browse/src/find-browse.ts', 'browse/dist/find-browse'),
    ('design/src/cli.ts', 'design/dist/design'),
    ('make-pdf/src/cli.ts', 'make-pdf/dist/pdf'),
    ('bin/gstack-global-discover.ts', 'bin/gstack-global-discover'),
)


class BuildInterrupted(RuntimeError):
    """Cancellation must not be swallowed as a retriable EINTR by subprocess."""


def read_json(path):
    if path.is_symlink() or not path.is_file():
        raise bundle.BundleError('runtime metadata must be a regular file')
    return json.loads(path.read_text(), object_pairs_hook=package.strict_object)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest_file(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(data)
    return hasher.hexdigest()


def regular_ancestors(path):
    for parent in (path, *path.parents):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise bundle.BundleError('runtime store has a linked or non-directory ancestor; preserve it and select a separate store')


def configuration(edition):
    record = package.load(edition)
    policy = read_json(edition / POLICY)
    if (not isinstance(policy, dict) or set(policy) != {'schema_version', 'bun_version', 'artifacts'}
            or policy['schema_version'] != 1 or policy['bun_version'] != package.BUN_VERSION
            or not isinstance(policy['artifacts'], dict) or not policy['artifacts']):
        raise bundle.BundleError('unreviewed runtime policy')
    names = {'linux-arm64': 'bun-linux-aarch64', 'linux-x64': 'bun-linux-x64-baseline'}
    for host, artifact in policy['artifacts'].items():
        if (host not in names or not isinstance(artifact, dict)
                or set(artifact) != {'url', 'sha256', 'size', 'member'}
                or artifact['url'] != f'https://github.com/oven-sh/bun/releases/download/bun-v{package.BUN_VERSION}/{names[host]}.zip'
                or artifact['member'] != names[host] + '/bun'
                or type(artifact['size']) is not int or not 0 < artifact['size'] <= package.MAX_ARCHIVE_BYTES
                or not isinstance(artifact['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', artifact['sha256'])):
            raise bundle.BundleError('invalid pinned Bun artifact')
    machine = platform.machine().lower()
    arch = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}.get(machine)
    host = f'linux-{arch}'
    if platform.system() != 'Linux' or host not in policy['artifacts']:
        raise bundle.BundleError('runtime build supports reviewed Linux arm64/x64 artifacts only; local discovery remains available')
    identity = {'package_sha256': bundle.digest(encoded(record)),
                'policy_sha256': bundle.digest(encoded(policy)),
                'build_revision': BUILD_REVISION, 'platform': host}
    return record, policy['artifacts'][host], identity


def tree(root):
    """Inventory every file, directory, mode and internal link without walking links."""
    if root.is_symlink() or not root.is_dir():
        raise bundle.BundleError('runtime payload must be an unlinked directory')
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise bundle.BundleError('runtime payload mode changed; preserve and reconcile it')
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            package.safe_path(relative)
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                link = os.readlink(path)
                if Path(link).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
                    raise bundle.BundleError('runtime link escapes the payload')
                result[relative] = {'link': link}
            elif stat.S_ISDIR(info.st_mode):
                result[relative] = {'directory': True, 'mode': mode}
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                result[relative] = {'sha256': digest_file(path), 'size': info.st_size, 'mode': mode}
            else:
                raise bundle.BundleError('nonregular or hard-linked runtime content')
    return result


def helper_launchers(record):
    """Keep original helper bytes/locations; bind their inherited interpreter."""
    names = {name.split('/')[1] for name, entry in record['source_files'].items()
             if name.startswith('bin/') and name.count('/') == 1 and entry.get('mode') == '100755'}
    names.update(output.split('/')[1] for _, output in BINARIES if output.startswith('bin/'))
    result = {}
    for name in sorted(names):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
            raise bundle.BundleError('unsafe helper launcher name')
        result[name] = ('#!/bin/sh\nset -eu\n'
                        'support=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)\n'
                        'PATH="$support/../bin:$PATH"\nexport PATH\n'
                        f'exec "$support/bin/{name}" "$@"\n').encode()
    return result


def validate_inventory(files, record, artifact, payload):
    """A local build receipt cannot substitute a sentinel for pinned material."""
    for name, entry in files.items():
        package.safe_path(name)
        if not isinstance(entry, dict):
            raise bundle.BundleError('invalid runtime inventory entry')
        if set(entry) == {'link'}:
            if not isinstance(entry['link'], str) or Path(entry['link']).is_absolute():
                raise bundle.BundleError('invalid runtime inventory link')
        elif set(entry) == {'directory', 'mode'}:
            if entry['directory'] is not True or type(entry['mode']) is not int:
                raise bundle.BundleError('invalid runtime inventory directory')
        elif (set(entry) != {'sha256', 'size', 'mode'} or type(entry['size']) is not int
              or entry['size'] < 0 or type(entry['mode']) is not int
              or not isinstance(entry['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', entry['sha256'])):
            raise bundle.BundleError('invalid runtime inventory file')
    required = {'source.tar': {'sha256': record['archive_sha256'], 'size': record['archive_size']},
                'bun.zip': {'sha256': artifact['sha256'], 'size': artifact['size']},
                'build/bun.lock': {'sha256': record['dependency_lock_sha256']}}
    for name, entry in record['source_files'].items():
        pinned = ({'link': entry['link']} if 'link' in entry else
                  {**entry, 'mode': int(entry['mode'][-3:], 8)})
        required['source/' + name] = pinned
        required['build/' + name] = pinned
    source_files = {p for p, v in files.items() if p.startswith('source/') and 'directory' not in v}
    if source_files != {'source/' + p for p in record['source_files']}:
        raise bundle.BundleError('runtime source inventory differs from pinned package')
    for row in record['skills'].values():
        host = row['codex']
        if host['status'] == 'available':
            for name, entry in host['files'].items():
                required[f'build/.agents/skills/{host["directory"]}/{name}'] = entry
    for name, data in helper_launchers(record).items():
        required['build/playbook-bin/' + name] = {'sha256': bundle.digest(data), 'size': len(data), 'mode': 0o755}
    saved_zip = payload / 'bun.zip'
    if saved_zip.is_file() and not saved_zip.is_symlink():
        if saved_zip.stat().st_size != artifact['size']:
            raise bundle.BundleError('pinned Bun archive size differs')
        executable = bun_executable(saved_zip.read_bytes(), artifact)
        required['bin/bun'] = {'sha256': bundle.digest(executable), 'size': len(executable), 'mode': 0o755}
    for name, expected in required.items():
        if any(files.get(name, {}).get(k) != v for k, v in expected.items()):
            raise bundle.BundleError('runtime inventory omits or changes required pinned material')
    outputs = ['bin/bun', *['build/' + output for _, output in BINARIES]]
    if (any('sha256' not in files.get(p, {}) or not files[p]['mode'] & 0o111 for p in outputs)
            or not any(p.startswith('build/node_modules/') and 'sha256' in v for p, v in files.items())):
        raise bundle.BundleError('runtime inventory omits required build outputs or dependencies')


def observe(target, identity, record, artifact):
    base = {'complete': False, 'path': str(target), 'identity': identity}
    if not target.exists() and not target.is_symlink():
        return {**base, 'status': 'missing'}
    if target.is_symlink() or not target.is_dir() or {p.name for p in target.iterdir()} != {'payload', 'receipt.json'}:
        raise bundle.BundleError('unknown runtime store content; preserve it and select a separate store')
    receipt = read_json(target / 'receipt.json')
    if (not isinstance(receipt, dict) or set(receipt) != {'schema_version', 'identity', 'files'} or receipt['schema_version'] != 1
            or receipt['identity'] != identity or not isinstance(receipt['files'], dict)
            or not receipt['files']):
        raise bundle.BundleError('runtime receipt identity differs from the adopted build; preserve it')
    actual = tree(target / 'payload')
    expected = receipt['files']
    validate_inventory(expected, record, artifact, target / 'payload')
    if set(actual) - set(expected) or any(actual[p] != expected[p] for p in actual):
        raise bundle.BundleError('runtime content changed or contains unknown entries; preserve customizations and choose a separate store')
    missing = sorted(set(expected) - set(actual))
    return {**base, 'complete': not missing, 'status': 'ready' if not missing else 'incomplete', 'missing': missing}


def download(artifact):
    request = urllib.request.Request(artifact['url'], headers={'User-Agent': 'playbook-pinned-runtime'})
    started = time.monotonic()
    parts, size = [], 0
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if not response.url.startswith('https://'):
                raise bundle.BundleError('Bun download did not retain HTTPS')
            while True:
                data = response.read(1024 * 1024)
                if not data:
                    break
                parts.append(data)
                size += len(data)
                if size > artifact['size'] or time.monotonic() - started > 600:
                    raise bundle.BundleError('Bun download exceeded its size or time bound')
    except OSError as error:
        raise bundle.BundleError('pinned Bun download failed; supply the exact archive or retry with network access') from error
    return b''.join(parts)


def inputs(record, artifact, target, source_archive, bun_archive, offline):
    def supplied_or_saved(supplied, filename):
        candidate = supplied if supplied is not None and supplied.exists() else target / 'payload' / filename
        if candidate.is_symlink():
            raise bundle.BundleError('input archives must be regular files')
        if candidate.is_file():
            if candidate.stat().st_size > package.MAX_ARCHIVE_BYTES:
                raise bundle.BundleError('input archive exceeds size limit')
            return candidate.read_bytes()
        return None
    source = supplied_or_saved(source_archive, 'source.tar')
    if source is None:
        if offline:
            raise bundle.BundleError('offline cold cache lacks the exact gstack source archive')
        source = package.committed_archive(record['source'], record['commit'])
    material = package.verified_archive(record, source)
    bun = supplied_or_saved(bun_archive, 'bun.zip')
    if bun is None:
        if offline:
            raise bundle.BundleError('offline cold cache lacks the exact Bun artifact')
        bun = download(artifact)
    return source, material, bun, bun_executable(bun, artifact)


def bun_executable(bun, artifact):
    if len(bun) != artifact['size'] or bundle.digest(bun) != artifact['sha256']:
        raise bundle.BundleError('Bun artifact integrity mismatch; restore the reviewed archive')
    try:
        with zipfile.ZipFile(io.BytesIO(bun)) as archive:
            entries = archive.infolist()
            members = [p for p in entries if not p.is_dir()]
            if (len(members) != 1 or members[0].filename != artifact['member']
                    or not 0 < members[0].file_size <= 256 * 1024 * 1024
                    or stat.S_ISLNK(members[0].external_attr >> 16)):
                raise bundle.BundleError('unexpected Bun archive inventory')
            executable = archive.read(members[0])
    except zipfile.BadZipFile as error:
        raise bundle.BundleError('invalid Bun archive') from error
    return executable


def execute(command, cwd, env):
    # Kill the process group on timeout; a shell/package subprocess must not keep
    # writing a staged tree after the provisioner reports failure.
    def terminate(signum, frame):
        raise BuildInterrupted('runtime command interrupted')

    previous_handler = signal.signal(signal.SIGTERM, terminate)
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, _ = process.communicate(timeout=600)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
    except subprocess.TimeoutExpired as error:
        raise bundle.BundleError('frozen runtime command exceeded 600 seconds; no fallback was attempted') from error
    except BuildInterrupted as error:
        raise bundle.BundleError('runtime command interrupted; process group stopped') from error
    except OSError as error:
        raise bundle.BundleError('required runtime command could not start') from error
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    if process.returncode:
        raise bundle.BundleError(f'frozen runtime command failed (exit {process.returncode}); no fallback was attempted')
    return stdout


def build(payload, record, source, material, bun_zip, executable):
    (payload / 'source.tar').write_bytes(source)
    (payload / 'bun.zip').write_bytes(bun_zip)
    (payload / 'bin').mkdir()
    bun = payload / 'bin/bun'
    bun.write_bytes(executable)
    bun.chmod(0o755)
    for name in ('source', 'build'):
        (payload / name).mkdir()
        package.extract(material, payload / name)
    work = payload / 'build'
    for parent in work.parents:
        if any((parent / p).exists() or (parent / p).is_symlink()
               for p in ('node_modules', 'package.json', 'bunfig.toml')):
            raise bundle.BundleError('ambient dependency ancestor; use a clean temporary directory')
    with tempfile.TemporaryDirectory(prefix='playbook-runtime-home-') as home:
        env = {'HOME': home, 'PATH': str(bun.parent) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8',
               'BUN_INSTALL_CACHE_DIR': home + '/cache', 'TMPDIR': home,
               'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD': '1'}
        if execute([str(bun), '--version'], work, env).decode().strip() != package.BUN_VERSION:
            raise bundle.BundleError('verified Bun artifact reports an unexpected version')
        commands = [[str(bun), 'install', '--frozen-lockfile', '--ignore-scripts', '--backend=copyfile'],
                    [str(bun), 'run', '--no-install', 'vendor:xterm'],
                    [str(bun), 'run', '--no-install', 'scripts/gen-skill-docs.ts', '--host', 'codex'],
                    *[[str(bun), 'build', '--compile', entry, '--outfile', output] for entry, output in BINARIES]]
        for command in commands:
            try:
                execute(command, work, env)
            except bundle.BundleError as error:
                raise bundle.BundleError('build step ' + ' '.join(command[1:]) + ': ' + str(error)) from error
        if digest_file(work / 'bun.lock') != record['dependency_lock_sha256']:
            raise bundle.BundleError('frozen build changed the dependency lock')
        for row in record['skills'].values():
            endpoint = row['codex']
            if endpoint['status'] == 'available':
                actual = package.endpoint(work / '.agents/skills', endpoint['directory'])
                if actual['files'] != endpoint['files']:
                    raise bundle.BundleError('runtime generation differs from reviewed host inventory')
        for _, output in BINARIES:
            path = work / output
            if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
                raise bundle.BundleError('native runtime output is missing or non-executable')
        launchers = work / 'playbook-bin'
        launchers.mkdir()
        for name, data in helper_launchers(record).items():
            launcher = launchers / name
            launcher.write_bytes(data)
            launcher.chmod(0o755)


def provision(edition, project, store, action, source_archive=None, bun_archive=None, offline=False):
    record, artifact, identity = configuration(edition)
    # Explicit storage is outside the project, its discovery roots and user roots.
    store = Path(os.path.abspath(store))
    regular_ancestors(store)
    physical = store.resolve()
    if (physical.is_relative_to(project.resolve()) or project.resolve().is_relative_to(physical)
            or any(p in ('.agents', '.codex', '.claude') for p in physical.parts)):
        raise bundle.BundleError('runtime store must be separate from the project and host discovery roots')
    target = physical / ('gstack-' + bundle.digest(encoded(identity)))
    status = observe(target, identity, record, artifact)
    if action == 'prepare-runtime' and not status['complete']:
        physical.mkdir(parents=True, exist_ok=True)
        lock = physical / '.gstack-runtime.lock'
        descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode) or os.fstat(descriptor).st_nlink != 1:
                raise bundle.BundleError('runtime lock must be a regular private file')
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise bundle.BundleError('another runtime build owns this store; retry after it finishes') from error
            status = observe(target, identity, record, artifact)
            if not status['complete']:
                source, material, bun_zip, executable = inputs(record, artifact, target, source_archive, bun_archive, offline)
                if offline:
                    raise bundle.BundleError('offline runtime is incomplete; a complete verified build cache is required')
                # Same-filesystem private stage: isolation without copying the
                # complete dependency tree a second time before publication.
                staged = Path(tempfile.mkdtemp(prefix='.gstack-staging-', dir=physical))
                try:
                    payload = staged / 'payload'
                    payload.mkdir(mode=0o700)
                    build(payload, record, source, material, bun_zip, executable)
                    inventory = tree(payload)
                    (staged / 'receipt.json').write_bytes(encoded({'schema_version': 1, 'identity': identity, 'files': inventory}))
                    if not observe(staged, identity, record, artifact)['complete']:
                        raise bundle.BundleError('runtime build was incomplete')
                    # Missing managed files can be repaired. Retain the entire
                    # earlier tree; changed or added material blocked above.
                    observe(target, identity, record, artifact)
                    if target.exists():
                        target.rename(physical / ('.gstack-previous-' + uuid.uuid4().hex))
                    staged.rename(target)
                finally:
                    if staged.exists():
                        shutil.rmtree(staged)  # Only our newly allocated stage.
        finally:
            os.close(descriptor)
        status = observe(target, identity, record, artifact)
    return {'schema_version': 1, 'complete': False, 'changed': [], 'skills': [],
            'runtime': status, 'scope': 'runtime-only', 'discovery': 'unverified',
            'qualification': 'unverified',
            'repair': None if status['complete'] else 'Prepare the exact runtime with network access; preserve conflicts or select a separate store.'}
