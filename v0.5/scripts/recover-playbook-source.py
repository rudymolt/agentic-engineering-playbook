#!/usr/bin/env python3
"""Reach the public provisioner through the consumer's exact adopted release."""
from __future__ import annotations

import argparse
import io
import os
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile

import release_provenance as provenance
import skill_adoption as adoption
import conductor_setup
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
        raise SourceError(f'source {source} does not match the clean adopted release, annotated tag object and commit; restore it or explicitly recover to a separate location')
    if not (source / 'v0.5' / bundle.BUNDLE / 'integrity.json').is_file():
        raise SourceError('adopted release lacks the skill bundle; explicitly upgrade through the existing migration gate')
    bundle.load(source / 'v0.5')
    cli = source / 'v0.5/scripts/provision-skills.py'
    if cli.is_symlink() or not cli.is_file():
        raise SourceError('adopted release lacks its regular public provisioner; explicitly upgrade or restore that release')
    return cli


def launcher_bytes():
    """Package the same provenance/reader code, not another release resolver."""
    scripts = Path(__file__).resolve().parent
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        entries = {'__main__.py': b'from source_recovery import main\nraise SystemExit(main())\n',
                   'source_recovery.py': Path(__file__).read_bytes(),
                   'LICENSE': (scripts.parents[1] / 'LICENSE').read_bytes(),
                   'conductor-setup.sh': (scripts / 'conductor-setup.sh').read_bytes()}
        for name in ('release_provenance.py', 'playbook_state.py', 'upstream_bundle.py',
                     'upstream_registry.py', 'skill_adoption.py', 'playbook_config.py', 'conductor_setup.py'):
            entries[name] = (scripts / name).read_bytes()
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()


def write_launcher(destination):
    data = launcher_bytes()
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


def missing_source(args, project, reason='is missing'):
    cache = shlex.quote(str(args.cache_dir) if args.cache_dir is not None else '<separate cache>')
    recover = (f'python3 .playbook/provision.pyz --project {shlex.quote(str(project))} --source '
               f'{shlex.quote(str(args.source))} --acquire --cache-dir {cache} preview')
    return SourceError(f'configured source {reason}: {args.source}; restore that exact checkout, or recover '
                       f'it explicitly with: {recover}. Local discovery never downloads; setup then '
                       'reuses the verified cache')


def resolve_source(args, project, proof):
    source = args.source.resolve()
    reason = 'is missing'
    if source.exists() or args.source.is_symlink():
        try:
            validate_source(source, proof)
            return source, 'reused'
        except SourceError:
            if args.cache_dir is None:
                raise
        # The configured checkout stays untouched; only the separate exact cache may serve.
        reason = 'differs from the adopted release'
    if args.cache_dir is None:
        raise missing_source(args, project)
    try:
        return cached_source(args, project, proof, reason)
    except SourceError as error:
        if reason == 'is missing':
            raise
        raise SourceError(f'configured source {reason} and is preserved: {args.source}; {error}; '
                          'restore that exact checkout or retry the explicit recovery') from None


def cached_source(args, project, proof, reason):
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
        raise missing_source(args, project, reason)
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


def join_repair(first, second):
    first = (first or '').strip()
    return (first if first.endswith(('.', ';')) else first + '.') + ' ' + second if first else second


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-launcher', type=Path, help='explicit portable zipapp output; preserves existing differing files')
    parser.add_argument('--acquire', action='store_true', help='explicit exact recovery; forbidden with local discovery')
    parser.add_argument('--candidate', action='store_true',
                        help='explicit setup of the maintainer checkout, never a consumer adoption')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--source', type=Path, help='configured checkout; never rewritten')
    parser.add_argument('--cache-dir', type=Path, help='separate exact-release storage')
    parser.add_argument('--repository', default=provenance.PUBLIC_REPOSITORY, help='acquisition transport, never release authority')
    parser.add_argument('action', nargs='?', default='discover', choices=('discover', 'preview', 'install', 'check', 'recover', 'retain', 'fallback', 'setup'))
    parser.add_argument('--skill')
    parser.add_argument('--custom-bindings-dir', type=Path)
    args = parser.parse_args(argv)
    try:
        setup = None
        if args.action == 'setup':
            if args.write_launcher is not None or args.skill is not None:
                raise SourceError('setup only replays inventory or discovers sources; run launcher export, '
                                  'retention or fallback as separate explicit commands')
            host = os.environ.get('CONDUCTOR_IS_LOCAL')
            if host not in ('0', '1'):
                raise SourceError('Conductor setup requires CONDUCTOR_IS_LOCAL=1 (local) or 0 (Cloud); '
                                  'restore the host-provided environment and retry setup')
            args.action = 'discover' if host == '1' else 'install'
            setup = {'host': 'local' if host == '1' else 'cloud', 'action': args.action}
        if args.write_launcher is not None:
            changed = write_launcher(args.write_launcher)
            print(json.dumps({'launcher': str(args.write_launcher), 'changed': changed}))
            return 0
        if args.project is None:
            raise SourceError('provide --project and the configured --source, or explicitly --write-launcher')
        if args.source is None and setup is not None and not args.candidate:
            state_file = args.project / '.playbook-state.yml'
            text = state_file.read_text() if state_file.is_file() else ''
            # Same rendered state-header location used by upgrade's recorded_playbook_root.
            matches = re.findall(r'^# Updated by stage files \(see (/.+?)/v0\.[345]/10-process/\*\)', text, re.M)
            if len(matches) != 1:
                raise SourceError('setup requires the recorded Playbook location in the state header; restore the rendered header or pass explicit --source')
            args.source = Path(matches[0])
        if args.source is None:
            raise SourceError('provide --project and the configured --source' + (
                '; candidate setup requires its explicit checkout' if args.candidate else ''))
        if args.acquire and args.action == 'discover':
            raise SourceError('local discovery never acquires source; select explicit --acquire with preview/install/check or recovery')
        project = args.project.resolve()
        if args.candidate:
            source = args.source.resolve()
            state = project / '.playbook-state.yml'
            if setup is None or project != source or state.exists() or state.is_symlink():
                raise SourceError('--candidate is only for explicit maintainer setup in its own checkout '
                                  'without consumer state; preserve consumer adoption and use its recorded release')
            if args.acquire or args.cache_dir is not None:
                raise SourceError('maintainer candidate setup never acquires a release; restore the candidate checkout')
            cli = source / 'v0.5/scripts/provision-skills.py'
            if cli.is_symlink() or not cli.is_file():
                raise SourceError('maintainer candidate lacks its regular provisioner; restore the candidate checkout')
            identity_args = ['--candidate']
            resolution = {'mode': 'maintainer-candidate', 'adoption_changed': False}
        else:
            proof = adopted_proof(project)
            record = adoption.setup_record(project) if setup is not None else None
            source, mode = resolve_source(args, project, proof)
            cli = validate_source(source, proof)
            if record is not None:
                adoption.validate_setup_inventory(project, source, proof, record)
            release, tag, commit = proof
            identity_args = ['--release', release, '--tag-object', tag, '--commit', commit]
            resolution = {'mode': mode, 'path': str(source), 'release': release,
                          'tag_object': tag, 'commit': commit, 'adoption_changed': False}
        command = [sys.executable, '-B', str(cli), '--project', str(project), '--source', str(source),
                   *identity_args, args.action]
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
        # A partial install still exits 2; prune whenever installation itself settled.
        if (args.action in ('install', 'recover') and 'error' not in result
                and not result.get('transaction_pending', True)):
            result['changed'] = [*result.get('changed', []), *conductor_setup.prune_aliases(project)]
        result['source_resolution'] = resolution
        if setup is not None:
            result['setup'] = setup
            _, packages, registry = bundle.load(source / 'v0.5')
            names = set(packages) | {name for name, skill in registry.skills.items()
                                     if skill.status == 'current' and registry.packages[skill.package].kind == 'local'}
            names.add('ai-playbook-deliver')  # Manifest-owned delivery skill, when bootstrap installed it.
            withheld = []
            settled = 'error' not in result and not result.get('transaction_pending', True)
            if setup['host'] == 'cloud':
                installed = {s['name'] for s in result.get('skills', [])
                             if s['installation'] in ('installed', 'customized')}
                # Pending or refused installs keep their own repair; only content conflicts are withheld then.
                withheld = [s for s in result.get('skills', []) if s['name'] not in installed
                            and (settled or s['installation'] == 'conflict')]
                names -= {s['name'] for s in withheld}
                if settled:
                    names -= set(packages) - installed
            rows, changed, conflicts = conductor_setup.discovery_aliases(
                project, names, apply=setup['host'] == 'cloud' and settled)
            for skill in withheld:
                alias = project / '.claude/skills' / skill['name']
                endpoint = ('linked' if alias.is_symlink() and os.readlink(alias) == '../../.agents/skills/' + skill['name']
                            else 'other' if alias.exists() or alias.is_symlink() else 'absent')
                rows.append({'runtime': 'codex', 'path': '.agents/skills/' + skill['name'],
                             'status': 'withheld', 'installation': skill['installation'],
                             'qualification': 'unverified'})
                # An existing endpoint is preserved; it resolves to unqualified project content.
                rows.append({'runtime': 'claude', 'path': '.claude/skills/' + skill['name'],
                             'status': 'withheld', 'endpoint': endpoint, 'qualification': 'unverified',
                             'repair_choices': skill['repair_choices']})
            result['discovery_aliases'] = rows
            result['changed'] = [*result.get('changed', []), *changed]
            if setup['host'] == 'cloud':
                result['installation_complete'] = result.get('complete', False)
                if withheld:
                    repairs = ['.claude/skills/' + s['name'] + ': ' +
                               ' '.join(s['repair_choices'] or ['Restore this skill through install.'])
                               for s in withheld]
                    result['repair'] = join_repair(result.get('repair'), 'Withheld aliases: ' + ' '.join(repairs))
                if conflicts:
                    endpoints = ', '.join(r['path'] for r in rows if r['status'] == 'conflict')
                    result['complete'] = False
                    result['repair'] = join_repair(result.get('repair'),
                                                   'Preserve conflicting Claude skill/command endpoints or linked discovery parents; explicitly reconcile '
                                                   + endpoints + ' before retrying. Other aliases and canonical Codex files remain available; '
                                                   'actual invocation is unverified.')
                    print(json.dumps(result, indent=2, sort_keys=True))
                    return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return run.returncode
    except (SourceError, OSError, ValueError, RuntimeError) as error:
        message = str(error) if isinstance(error, ValueError) else 'cannot access the adopted source or release proof; restore readable inputs and retry'
        print(json.dumps({'complete': False, 'changed': [], 'error': message,
                          'repair': message, 'adoption_changed': False}, indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
