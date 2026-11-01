"""Pinned gstack source and generated-host contract; no host activation authority."""
from __future__ import annotations

import io
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import tarfile
import tempfile

import upstream_bundle as bundle
import upstream_registry

PACKAGE = 'gstack'
RECORD = Path('bundles/gstack/integrity.json')
BUN_VERSION = '1.4.4'
SAFETY_SKILLS = {'careful', 'freeze', 'guard', 'unfreeze'}
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024


def run(command, *, cwd=None, env=None, timeout=120):
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise bundle.BundleError('required package command unavailable or exceeded its time limit') from error
    if result.returncode:
        raise bundle.BundleError(f'package command failed (exit {result.returncode}); no fallback was attempted')
    return result.stdout


def safe_path(name):
    path = PurePosixPath(name)
    if (not name or not path.parts or path.is_absolute() or '..' in path.parts or path.as_posix() != name
            or '\\' in name or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise bundle.BundleError('unsafe package path')
    return path


def safe_alias(link):
    # The pinned source has sibling-only aliases. A wider link grammar needs
    # separate review; lexical '..' normalization is not filesystem resolution.
    if (not isinstance(link, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+', link)
            or link in ('.', '..')):
        raise bundle.BundleError('unsupported source alias; only sibling aliases are reviewed')


def archive_files(data):
    """Validate the entire archive before writing or following any link."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise bundle.BundleError('source archive exceeds the supported size')
    material = {}
    directories = set()
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
            for entry in archive:
                name = entry.name.rstrip('/') if entry.isdir() else entry.name
                safe_path(name)
                if name in material or name in directories:
                    raise bundle.BundleError('duplicate source archive path')
                if entry.isdir():
                    directories.add(name)
                    continue
                if entry.isfile():
                    total += entry.size
                    if total > MAX_ARCHIVE_BYTES or len(material) >= 20000:
                        raise bundle.BundleError('expanded source archive exceeds the supported size')
                    material[name] = {'bytes': archive.extractfile(entry).read(),
                                      'mode': '100755' if entry.mode & 0o111 else '100644'}
                elif entry.issym():
                    # Only source-observed internal relative aliases are eligible.
                    safe_alias(entry.linkname)
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), entry.linkname))
                    safe_path(target)
                    material[name] = {'link': entry.linkname, 'target': target}
                else:
                    raise bundle.BundleError('nonregular source archive member')
    except (tarfile.TarError, OSError) as error:
        raise bundle.BundleError('unreadable source archive') from error
    for name, entry in material.items():
        if any(p.as_posix() in material for p in PurePosixPath(name).parents):
            raise bundle.BundleError('overlapping source archive paths')
        if 'link' in entry:
            seen = {name}
            target = entry['target']
            while target in material and 'link' in material[target]:
                if target in seen:
                    raise bundle.BundleError('cyclic source alias')
                seen.add(target)
                target = material[target]['target']
            if target not in material and target not in directories:
                raise bundle.BundleError('dangling source alias')
    return material


def source_records(material):
    return {name: ({'link': entry['link']} if 'link' in entry else
                   {'sha256': bundle.digest(entry['bytes']), 'size': len(entry['bytes']), 'mode': entry['mode']})
            for name, entry in sorted(material.items())}


def extract(material, destination):
    # destination is a new private staging directory, never an existing install.
    for name, entry in material.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if 'bytes' in entry:
            path.write_bytes(entry['bytes'])
            path.chmod(int(entry['mode'][-3:], 8))
    for name, entry in material.items():
        if 'link' in entry:
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(entry['link'])


def selected(registry):
    return sorted(registry.skills_for(PACKAGE), key=lambda skill: skill.name)


def codex_name(name):
    if name == 'connect-chrome':
        return 'gstack-open-gstack-browser'
    return name if name == 'gstack-upgrade' else 'gstack-' + name


def endpoint(root, directory):
    path = (root / directory).resolve(strict=True)
    if not path.is_relative_to(root.resolve()):
        raise bundle.BundleError('host endpoint escapes verified source')
    material = bundle.files(path)
    text = material.get('SKILL.md', b'').decode('utf-8')
    head = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
    names = re.findall(r'^name: ([a-z][a-z0-9-]*)$', head[1], re.M) if head else []
    if len(names) != 1:
        raise bundle.BundleError(f'{directory}: missing unambiguous host name')
    return {'status': 'available', 'directory': directory, 'declared_name': names[0],
            'files': {p: {'sha256': bundle.digest(b), 'size': len(b)} for p, b in sorted(material.items())}}


def generate(edition, upstream, bun):
    registry = upstream_registry.load(edition / 'upstream-skills.json')
    package = registry.packages[PACKAGE]
    commit = package.pin['commit']
    data = committed_archive(upstream, commit)
    material = archive_files(data)
    if material.get('VERSION', {}).get('bytes', b'').decode().strip() != package.pin['value']:
        raise bundle.BundleError('source VERSION differs from registry pin')
    if b'MIT License' not in material.get('LICENSE', {}).get('bytes', b''):
        raise bundle.BundleError('source is missing the upstream MIT notice')
    lock = material.get('bun.lock', {}).get('bytes')
    if lock is None:
        raise bundle.BundleError('source is missing its frozen dependency lock')
    if run([bun, '--version']).decode().strip() != BUN_VERSION:
        raise bundle.BundleError(f'generation requires Bun {BUN_VERSION}; select the reviewed runtime explicitly')
    with tempfile.TemporaryDirectory(prefix='playbook-gstack-') as tmp:
        source = Path(tmp).resolve(strict=True) / 'source'
        source.mkdir()
        extract(material, source)
        # Refuse ambient ancestor packages/configuration instead of allowing Bun
        # to resolve dependencies outside the disposable, frozen package tree.
        for parent in source.parents:
            if any((parent / p).exists() or (parent / p).is_symlink()
                   for p in ('node_modules', 'package.json', 'bunfig.toml')):
                raise bundle.BundleError('ambient dependency ancestor; use a clean temporary directory')
        env = {k: v for k, v in os.environ.items()
               if not k.upper().startswith(('BUN_', 'NODE_', 'NPM_', 'XDG_'))}
        env.update(HOME=str(Path(tmp) / 'home'), BUN_INSTALL_CACHE_DIR=str(Path(tmp) / 'bun-cache'))
        Path(env['HOME']).mkdir()
        skills = {s.name: {'invocation': s.invocation, 'claude': endpoint(source, s.name)}
                  for s in selected(registry)}
        run([bun, 'install', '--frozen-lockfile', '--ignore-scripts'], cwd=source, env=env, timeout=600)
        if (source / 'bun.lock').read_bytes() != lock:
            raise bundle.BundleError('frozen install changed the dependency lock')
        run([bun, 'run', '--no-install', 'scripts/gen-skill-docs.ts', '--host', 'codex'], cwd=source, env=env)
        for name, row in skills.items():
            if name == 'codex':
                row['codex'] = {'status': 'unsupported', 'reason': 'Upstream intentionally excludes its Claude Codex wrapper on Codex.'}
            else:
                row['codex'] = endpoint(source / '.agents/skills', codex_name(name))
                if name in SAFETY_SKILLS:
                    row['codex']['enforcement'] = 'unsupported'
    return validate({'schema_version': 1, 'package': PACKAGE, 'source': package.source,
            'version': package.pin['value'], 'commit': commit,
            'archive_sha256': bundle.digest(data), 'archive_size': len(data),
            'source_files': source_records(material), 'dependency_lock_sha256': bundle.digest(lock),
            'generator': generator_contract(),
            'skills': skills}, registry)


def committed_archive(upstream, commit):
    """Ignore local replacements, info/attributes and user export settings."""
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise bundle.BundleError('invalid pinned commit')
    with tempfile.TemporaryDirectory(prefix='playbook-gstack-git-') as tmp:
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_NO_REPLACE_OBJECTS='1', GIT_CONFIG_NOSYSTEM='1',
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
        run(['git', 'init', '--bare', '--template=', tmp], env=env)
        run(['git', '-C', tmp, 'fetch', '--no-tags', '--depth=1', str(upstream), commit], env=env)
        if run(['git', '-C', tmp, 'rev-parse', 'FETCH_HEAD^{commit}'], env=env).decode().strip() != commit:
            raise bundle.BundleError('upstream does not contain the exact registry commit')
        data = run(['git', '-C', tmp, 'archive', '--format=tar', commit], env=env)
        material = archive_files(data)
        expected = {}
        for item in run(['git', '-C', tmp, 'ls-tree', '-rz', commit], env=env).split(b'\0'):
            if not item:
                continue
            metadata, path = item.split(b'\t', 1)
            mode, kind, sha = metadata.decode().split()
            if kind != 'blob':
                raise bundle.BundleError('source submodules require separate reviewed packaging')
            expected[path.decode('utf-8')] = (mode, sha)
        observed = {}
        for name, entry in material.items():
            raw = entry['link'].encode() if 'link' in entry else entry['bytes']
            sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            observed[name] = ('120000' if 'link' in entry else entry['mode'], sha)
        if observed != expected:
            raise bundle.BundleError('source archive differs from the complete canonical Git tree')
        return data


def generator_contract():
    return {'bun_version': BUN_VERSION, 'host': 'codex', 'respect_detection': False,
            'dependencies': 'frozen-lockfile', 'lifecycle_scripts': False, 'auto_install': False}


def record_path(edition):
    path = edition / RECORD
    for parent in (path.parent.parent, path.parent):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise bundle.BundleError('preserve linked or non-directory package destination')
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise bundle.BundleError('package record must be a regular file')
    return path


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise bundle.BundleError('duplicate package record key')
        result[key] = value
    return result


def load(edition):
    registry = upstream_registry.load(edition / 'upstream-skills.json')
    record = json.loads(record_path(edition).read_text(), object_pairs_hook=strict_object)
    return validate(record, registry)


def validate(record, registry):
    if not isinstance(record, dict) or set(record) != {
            'schema_version', 'package', 'source', 'version', 'commit', 'archive_sha256',
            'archive_size', 'source_files', 'dependency_lock_sha256', 'generator', 'skills'}:
        raise bundle.BundleError('invalid gstack package record')
    package = registry.packages[PACKAGE]
    if (record.get('schema_version') != 1 or record.get('package') != PACKAGE
            or record.get('source') != package.source or record.get('commit') != package.pin['commit']
            or record.get('version') != package.pin['value']
            or set(record.get('skills', {})) != {s.name for s in selected(registry)}):
        raise bundle.BundleError('gstack record differs from registry identity or selected inventory')
    if record.get('generator') != generator_contract():
        raise bundle.BundleError('unreviewed gstack generator contract')
    for key in ('archive_sha256', 'dependency_lock_sha256'):
        if not isinstance(record.get(key), str) or not re.fullmatch('[a-f0-9]{64}', record[key]):
            raise bundle.BundleError('invalid gstack source digest')
    if type(record.get('archive_size')) is not int or not 0 < record['archive_size'] <= MAX_ARCHIVE_BYTES:
        raise bundle.BundleError('invalid gstack archive size')
    validate_source_records(record.get('source_files'))
    if record.get('source_files', {}).get('bun.lock', {}).get('sha256') != record['dependency_lock_sha256']:
        raise bundle.BundleError('dependency lock differs from source inventory')
    for skill in selected(registry):
        row = record['skills'][skill.name]
        if row.get('invocation') != skill.invocation or set(row) != {'invocation', 'claude', 'codex'}:
            raise bundle.BundleError('host invocation contract differs from registry')
        for host in ('claude', 'codex'):
            item = row[host]
            if host == 'codex' and skill.name == 'codex':
                if item.get('status') != 'unsupported' or not item.get('reason'):
                    raise bundle.BundleError('Codex wrapper exclusion is missing')
                continue
            directory = skill.name if host == 'claude' else codex_name(skill.name)
            expected_name = 'open-gstack-browser' if skill.name == 'connect-chrome' else skill.name
            if (item.get('status') != 'available' or item.get('directory') != directory
                    or item.get('declared_name') != expected_name or 'SKILL.md' not in item.get('files', {})):
                raise bundle.BundleError('host endpoint mapping differs from reviewed source contract')
            if host == 'codex' and skill.name in SAFETY_SKILLS and item.get('enforcement') != 'unsupported':
                raise bundle.BundleError('Codex safety enforcement exception is missing')
            for name, metadata in item['files'].items():
                safe_path(name)
                if any(p.as_posix() in item['files'] for p in PurePosixPath(name).parents):
                    raise bundle.BundleError('overlapping host inventory paths')
                if (set(metadata) != {'sha256', 'size'} or type(metadata['size']) is not int or metadata['size'] < 0
                        or not re.fullmatch('[a-f0-9]{64}', metadata['sha256'])):
                    raise bundle.BundleError('invalid host file integrity')
        prefix = resolve_alias(record['source_files'], skill.name) + '/'
        source_content = {p[len(prefix):]: {k: v for k, v in metadata.items() if k != 'mode'}
                          for p, metadata in record['source_files'].items() if p.startswith(prefix)}
        if row['claude']['files'] != source_content:
            raise bundle.BundleError('Claude directory integrity differs from verified source inventory')
    return record


def validate_source_records(records):
    if not isinstance(records, dict) or not records or len(records) > 20000:
        raise bundle.BundleError('invalid source file inventory')
    for name, entry in records.items():
        safe_path(name)
        if any(p.as_posix() in records for p in PurePosixPath(name).parents):
            raise bundle.BundleError('overlapping source inventory paths')
        if not isinstance(entry, dict):
            raise bundle.BundleError('invalid source file entry')
        if set(entry) == {'link'}:
            link = entry['link']
            safe_alias(link)
            safe_path(posixpath.normpath(posixpath.join(posixpath.dirname(name), link)))
            target = resolve_alias(records, name)
            if target not in records and not any(p.startswith(target + '/') for p in records):
                raise bundle.BundleError('dangling source alias')
        elif (set(entry) != {'sha256', 'size', 'mode'}
              or entry['mode'] not in ('100644', '100755')
              or type(entry['size']) is not int or not 0 <= entry['size'] <= MAX_ARCHIVE_BYTES
              or not isinstance(entry['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', entry['sha256'])):
            raise bundle.BundleError('invalid source file integrity')


def resolve_alias(records, name):
    seen = set()
    while name in records and 'link' in records[name]:
        if name in seen:
            raise bundle.BundleError('cyclic source alias')
        seen.add(name)
        name = posixpath.normpath(posixpath.join(posixpath.dirname(name), records[name]['link']))
        safe_path(name)
    return name


def verified_archive(record, data):
    if len(data) != record['archive_size'] or bundle.digest(data) != record['archive_sha256']:
        raise bundle.BundleError('gstack source archive integrity mismatch; restore the pinned archive')
    material = archive_files(data)
    if source_records(material) != record['source_files']:
        raise bundle.BundleError('archive file inventory differs from adopted package')
    return material
