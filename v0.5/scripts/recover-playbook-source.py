#!/usr/bin/env python3
"""Reach the public provisioner through the consumer's exact adopted release."""
from __future__ import annotations

import argparse
import io
import os
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

import release_provenance as provenance
from playbook_state import parse_scalar, top_level_scalar_value
import upstream_bundle as bundle


class SourceError(ValueError):
    """An exact adopted source needs explicit recovery, never an upgrade."""


def adopted_proof(project):
    state = project / '.playbook-state.yml'
    if not state.is_file():
        raise SourceError('adopted proof must be a regular file; preserve the nonregular or missing .playbook-state.yml endpoint and restore a readable regular adoption record')
    text = state.read_text()
    keys = ('playbook_release', 'playbook_release_tag_object', 'playbook_release_commit')
    values = []
    for key in keys:
        if len(re.findall(r'^' + key + r':', text, re.M)) != 1:
            raise SourceError('missing or ambiguous adopted release proof; restore the recorded release, annotated tag object and commit')
        values.append(parse_scalar(top_level_scalar_value(text, key) or 'null'))
    release, tag, commit = values
    if (not isinstance(release, str) or not provenance.RELEASE_TAG.fullmatch(release)
            or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{40}', v) for v in (tag, commit))):
        raise SourceError('missing or invalid adopted release proof; restore the recorded release, annotated tag object and commit')
    return release, tag, commit


def validate_source(source, proof):
    if not provenance.local_checkout_matches_release(source, *proof):
        raise SourceError('source does not match the clean adopted release, annotated tag object and commit; restore it or explicitly recover to a separate location')
    if not (source / 'v0.5' / bundle.BUNDLE / 'integrity.json').is_file():
        raise SourceError('adopted release lacks the skill bundle; explicitly upgrade through the existing migration gate')
    bundle.load(source / 'v0.5')
    cli = source / 'v0.5/scripts/provision-skills.py'
    if cli.is_symlink() or not cli.is_file():
        raise SourceError('adopted release lacks its regular public provisioner; explicitly upgrade or restore that release')
    return cli


def write_launcher(destination):
    """Package the same provenance/reader code, not another release resolver."""
    scripts = Path(__file__).resolve().parent
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        entries = {'__main__.py': b'from source_recovery import main\nraise SystemExit(main())\n',
                   'source_recovery.py': Path(__file__).read_bytes(),
                   'LICENSE': (scripts.parents[1] / 'LICENSE').read_bytes()}
        for name in ('release_provenance.py', 'playbook_state.py', 'upstream_bundle.py', 'upstream_registry.py'):
            entries[name] = (scripts / name).read_bytes()
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    data = output.getvalue()
    if destination.is_symlink():
        raise SourceError('launcher destination is linked; preserve and reconcile it explicitly')
    if destination.exists():
        if not destination.is_file():
            raise SourceError('launcher destination must be a regular file; preserve the nonregular endpoint and choose another output')
        if destination.read_bytes() != data:
            raise SourceError('launcher destination differs; preserve customizations and choose another output')
        return False
    with destination.open('xb') as stream:
        stream.write(data)
    return True


def acquisition_git(directory, *args):
    try:
        run = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull,
                              '-c', 'core.fsmonitor=false', '-C', str(directory), *args],
                             capture_output=True, timeout=30,
                             env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    except (OSError, subprocess.TimeoutExpired):
        raise SourceError('exact release acquisition unavailable or timed out; restore repository access and retry explicitly') from None
    if run.returncode:
        raise SourceError('exact release acquisition unavailable; check repository access and the adopted tag, then retry explicitly')


def resolve_source(args, project, proof):
    source = args.source.resolve()
    if source.exists() or args.source.is_symlink():
        validate_source(source, proof)
        return source, 'reused'
    if args.cache_dir is None:
        raise SourceError('configured source is missing; select a separate --cache-dir and explicit --acquire for recovery')
    cache = args.cache_dir.resolve()
    if cache.is_relative_to(project) or args.cache_dir.is_symlink():
        raise SourceError('exact source cache must be an unlinked directory outside the consumer project and its customizations')
    release, tag, commit = proof
    target = cache / (release + '-' + tag + '-' + commit)
    if target.is_symlink():
        raise SourceError('cached source is linked; preserve it and explicitly choose a separate cache')
    if target.exists():
        validate_source(target, proof)
        return target, 'reused'
    if not args.acquire:
        raise SourceError('configured source is missing; use explicit --acquire with a non-discovery action; local discovery never downloads')
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.recover-', dir=cache) as temporary:
        checkout = Path(temporary) / 'checkout'
        checkout.mkdir()
        acquisition_git(checkout, 'init', '--quiet', '--template=')
        acquisition_git(checkout, 'fetch', '--no-tags', '--depth=1', '--', args.repository,
                        'refs/tags/' + release + ':refs/tags/' + release)
        if (provenance.git_output(checkout, 'cat-file', '-t', 'refs/tags/' + release) != 'tag'
                or provenance.git_output(checkout, 'rev-parse', 'refs/tags/' + release) != tag
                or provenance.git_output(checkout, 'rev-parse', 'refs/tags/' + release + '^{}') != commit):
            raise SourceError('fetched tag object or commit differs from adopted proof; preserve adoption and reconcile the moved tag or wrong source')
        acquisition_git(checkout, 'checkout', '--quiet', '--detach', commit)
        validate_source(checkout, proof)
        checkout.rename(target)
    return target, 'acquired'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-launcher', type=Path, help='explicit portable zipapp output; preserves existing differing files')
    parser.add_argument('--acquire', action='store_true', help='explicit exact recovery; forbidden with local discovery')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--source', type=Path, help='configured checkout; never rewritten')
    parser.add_argument('--cache-dir', type=Path, help='separate exact-release storage')
    parser.add_argument('--repository', default=provenance.PUBLIC_REPOSITORY, help='acquisition transport, never release authority')
    parser.add_argument('action', nargs='?', default='discover', choices=('discover', 'preview', 'install', 'check', 'recover', 'retain', 'fallback'))
    parser.add_argument('--skill')
    parser.add_argument('--custom-bindings-dir', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.write_launcher is not None:
            changed = write_launcher(args.write_launcher)
            print(json.dumps({'launcher': str(args.write_launcher), 'changed': changed}))
            return 0
        if args.project is None or args.source is None:
            raise SourceError('provide --project and the configured --source, or explicitly --write-launcher')
        if args.acquire and args.action == 'discover':
            raise SourceError('local discovery never acquires source; select explicit --acquire with preview/install/check or recovery')
        project = args.project.resolve()
        proof = adopted_proof(project)
        source, mode = resolve_source(args, project, proof)
        cli = validate_source(source, proof)
        release, tag, commit = proof
        command = [sys.executable, '-B', str(cli), '--project', str(project), '--source', str(source),
                   '--release', release, '--tag-object', tag, '--commit', commit, args.action]
        if args.skill is not None:
            command += ['--skill', args.skill]
        if args.custom_bindings_dir is not None:
            command += ['--custom-bindings-dir', str(args.custom_bindings_dir)]
        run = subprocess.run(command, capture_output=True, text=True)
        try:
            result = json.loads(run.stdout)
            if not isinstance(result, dict):
                raise ValueError('object required')
        except ValueError:
            raise SourceError('verified release provisioner failed without a JSON report; inspect that release and restore its supported interface') from None
        result['source_resolution'] = {'mode': mode, 'path': str(source), 'release': release,
                                       'tag_object': tag, 'commit': commit, 'adoption_changed': False}
        print(json.dumps(result, indent=2, sort_keys=True))
        return run.returncode
    except (SourceError, OSError, ValueError, RuntimeError) as error:
        message = str(error) if isinstance(error, ValueError) else 'cannot access the adopted source or release proof; restore readable inputs and retry'
        print(json.dumps({'complete': False, 'changed': [], 'error': message,
                          'repair': message, 'adoption_changed': False}, indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
