#!/usr/bin/env python3
"""Manage the registry-selected project skill bundle and previous installation.

With no action, discover local sources without writes.
Exit 0: successful report/command; 2: incomplete check, partial install or blocked operation.
All commands emit JSON. Discovery can report blocked jobs; it never runs them.
Installation requires an explicit command and source proof.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

import release_provenance as provenance
import upstream_bundle as bundle
import upstream_registry
import provisioning_state as history
from skill_bindings import JobBindings, JOBS
from playbook_config import Configuration, ConfigError, public_error_message


_spec = importlib.util.spec_from_file_location(
    'provisioning_compatibility', Path(__file__).with_name('check-upstream-compatibility.py'))
assert _spec and _spec.loader
compatibility = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compatibility)


class ProvisionError(ValueError):
    """Provisioning requires a repair or explicit source selection."""


def source_identity(args) -> dict:
    root = args.source.resolve()
    if args.candidate:
        head = provenance.git_output(root, 'rev-parse', 'HEAD')
        if head is None or provenance.git_output(root, 'rev-parse', '--show-toplevel') != str(root):
            raise ProvisionError('candidate must be a Playbook Git checkout')
        return {'kind': 'maintainer-candidate', 'commit': head, 'release': None,
                'dirty': provenance.clean_checkout_head(root) is None}
    proof = (args.release, args.tag_object, args.commit)
    if any(proof):
        if not all(proof) or not provenance.local_checkout_matches_release(root, *proof):
            raise ProvisionError('recorded release proof does not match a clean checkout; restore the exact adopted tag object and commit')
        release, tag_object, commit = proof
    else:
        verified = provenance.verified_release_evidence(root)
        if verified is None:
            raise ProvisionError('source release is unverified; restore the adopted release and its recorded proof, or explicitly select --candidate for maintainer testing')
        release, tag_object, commit = verified
    return {'kind': 'verified-release', 'release': release, 'tag_object': tag_object,
            'commit': commit, 'proof': 'recorded-local' if any(proof) else 'public-tag'}


def installation_status(path: Path, expected: dict[str, bytes]) -> str:
    if not path.exists() and not path.is_symlink():
        return 'missing'
    try:
        actual = bundle.files(path)
    except (bundle.BundleError, OSError):
        return 'conflict'
    return 'installed' if actual == expected else 'conflict'


def installed_matches_history(project, name, state):
    try:
        return history.actual(project, name) == history.content(state['current'], name)
    except (bundle.BundleError, OSError):
        return False


def inspect(project, identity, manifest, packages, registry, edition):
    state = history.load(project)
    retained = history.retained(project)
    rows = []
    integrations = compatibility.load_manifest(edition / 'upstream-integrations.json')
    problems = upstream_registry.manifest_problems(registry, integrations)
    if problems:
        raise ProvisionError('invalid integration manifest: ' + '; '.join(problems))
    for name, content in packages.items():
        skill = registry.skills[name]
        integration = integrations['integrations'].get(skill.manifest_key) if skill.manifest_key else None
        # Reuse the existing compatibility record; never grant eligibility by copying.
        compatible = None
        fallback = None
        if integration:
            matches = bundle.digest(content['SKILL.md']) == integration.get('tested_source_sha256')
            compatible = integration.get('embedded_compatible') if matches else None
            fallback = integration.get('fallback')
        target = project / '.agents/skills' / name
        status = installation_status(target, content)
        if status == 'conflict' and installed_matches_history(project, name, state):
            status = 'update_available'
        try:
            actual = bundle.files(target)
            installed_integrity = {p: bundle.digest(b) for p, b in actual.items()}
        except (bundle.BundleError, OSError):
            installed_integrity = None
        retention_error = None
        if name in retained['skills']:
            try:
                history.retained_content(project, name, retained, skill, content['LICENSE'])
                status = 'customized'
                compatible = False if compatible is False else None
            except (history.StateError, bundle.BundleError, OSError) as error:
                status = 'conflict'
                retention_error = str(error)
        rows.append({
            'name': name,
            'path': f'.agents/skills/{name}',
            'installation': status,
            'installed_source': ('project-customization' if status == 'customized' else
                                 manifest['commit'] if status == 'installed' else 'unknown'),
            'managed_source': state['current']['source'] if state['current'] and installed_matches_history(project, name, state) else None,
            'retention': retained['skills'].get(name),
            'retention_error': retention_error,
            'repair_choices': ([
                'Commit and explicitly retain --skill ' + name + ' after finishing any pending transaction.',
                'Move later or unknown material outside this skill directory and restore recorded bytes before retrying.',
            ] if status == 'conflict' else []),
            'installed_integrity': installed_integrity,
            'integrity': {p: bundle.digest(data) for p, data in sorted(content.items())},
            'upstream': {k: manifest[k] for k in ('source', 'version', 'commit', 'tag_object')},
            'invocation': skill.invocation,
            'dependencies': list(skill.dependencies),
            'embedded_compatible': compatible,
            'fallback': fallback,
            'discovery': 'unverified',
            'qualification': 'unverified',
        })
    complete = all(s['installation'] in ('installed', 'customized') for s in rows) and state['transaction'] is None
    return {'schema_version': 1, 'source': identity, 'skills': rows,
            'complete': complete, 'changed': [],
            'retained_outside_inventory': sorted(set(retained['skills']) - set(packages)),
            'transaction_pending': state['transaction'] is not None,
            'repair': (None if complete else
                       'Interrupted replacement: retry the identical install or select recover; move later edits aside first.'
                       if state['transaction'] else
                       'Rerun install for missing or unchanged managed skills; explicitly retain committed customizations or move conflicts aside.')}


def local_revision(path, baseline):
    """Report proven Git ancestry only; tags and ordering grant no eligibility."""
    root = provenance.git_output(path.parent, 'rev-parse', '--show-toplevel')
    unknown = {'version': None, 'commit': None, 'revision_relation': 'unknown',
               'working_tree_changed': None}
    if root is None:
        return unknown
    root = Path(root).resolve()
    head = provenance.git_output(root, 'rev-parse', 'HEAD')
    ancestor = provenance.git_output(root, 'merge-base', baseline, head) if head else None
    relation = 'exact' if head == baseline else 'newer' if ancestor == baseline else 'unknown'
    if relation == 'unknown':
        return unknown
    relative = path.parent.relative_to(root)
    status = provenance.git_output(root, '--no-optional-locks', 'status', '--porcelain', '--untracked-files=all', '--ignored=matching', '--', relative.as_posix())
    return {'version': provenance.git_output(root, 'describe', '--tags', '--exact-match', 'HEAD'),
            'commit': head, 'revision_relation': relation,
            'working_tree_changed': None if status is None else bool(status)}


def discover_local(project, identity, manifest, packages, registry, edition, custom_dir=None):
    catalog = JobBindings(project, registry=registry, manifest=edition / "upstream-integrations.json",
                          custom_dir=custom_dir)
    rows = []
    for name, expected in packages.items():
        skill = registry.skills[name]
        sources = []
        for path in catalog.source_paths(skill):
            try:
                if path in catalog.source_failures.get(f'{skill.package}:{name}', set()):
                    raise bundle.BundleError('unknown source entry or directory')
                actual = bundle.files(path.parent)
                difference = {'added': sorted(set(actual) - set(expected)),
                              'missing': sorted(set(expected) - set(actual)),
                              'changed': sorted(p for p in actual.keys() & expected.keys()
                                                if actual[p] != expected[p])}
                revision = local_revision(path, manifest['commit'])
                content = ('exact' if actual == expected else
                           'newer' if revision['revision_relation'] == 'newer'
                           and revision['working_tree_changed'] is False else 'customized')
                sources.append({'path': str(path), **revision,
                                'content': content,
                                'difference': difference,
                                'integrity': {p: bundle.digest(b) for p, b in sorted(actual.items())}})
            except (bundle.BundleError, OSError, RuntimeError, UnicodeError):
                sources.append({'path': str(path), 'version': None, 'content': 'unknown',
                                'difference': None, 'integrity': None,
                                'repair': 'Preserve and inspect the entry and complete source tree; restore readable regular skill files and directory enumeration access, or alias the complete directory before selecting it.'})
        status = ('missing' if not sources else 'duplicate' if len(sources) > 1 else
                  sources[0]['content'])
        rows.append({'name': name, 'source_id': f'{skill.package}:{name}',
                     'status': status, 'sources': sources, 'invocation': skill.invocation,
                     'blocked': status in ('duplicate', 'unknown'),
                     'repair': ('Resolve distinct-source command collision explicitly before using this route.'
                                if status == 'duplicate' else
                                'Preserve and inspect the entry and complete source tree; restore readable regular skill files and directory enumeration access, or alias the complete directory before selecting it.'
                                if status == 'unknown' else None),
                     'baseline': {k: manifest[k] for k in ('source', 'version', 'commit')},
                     'qualification': 'unverified'})
    service = Configuration(project, None, bindings=catalog)
    routes, options = {}, {}
    with catalog.inventory_scope():
        for job, contract in JOBS.items():
            options[job] = catalog.options(job)
            try:
                routes[job] = service.dispatch_job(job, contract['owner'])
            except (ConfigError, OSError, RuntimeError, UnicodeError) as error:
                routes[job] = {'state': 'blocked', 'launched': False,
                               'message': public_error_message(error)}
    return {'schema_version': 1, 'source': identity, 'local_sources': rows,
            'job_routes': routes, 'job_options': options, 'job_rejections': catalog.rejections,
            'changed': [], 'runtime_resolution': 'unverified', 'complete': False,
            'repair': 'Select eligible sources through Configure preview/Apply and the owning stage; actual invocation evidence is required.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='existing destination project')
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2],
                        help='available Playbook Git checkout; no acquisition is performed')
    parser.add_argument('--candidate', action='store_true', help='explicit maintainer testing; never a consumer release')
    parser.add_argument('--release', help='previously verified release tag')
    parser.add_argument('--tag-object', help='previously verified annotated tag object')
    parser.add_argument('--commit', help='previously verified release commit')
    parser.add_argument('--custom-bindings-dir', type=Path,
                        help='existing external machine-local bindings/audits, read-only; same store as Configure')
    parser.add_argument('--skill', help='one registry-selected skill for retention or manual fallback')
    parser.add_argument('action', nargs='?', default='discover', choices=('discover', 'preview', 'install', 'check', 'recover', 'retain', 'fallback'))
    args = parser.parse_args(argv)
    report = {'schema_version': 1, 'complete': False, 'changed': [], 'skills': []}
    inspection = None
    try:
        if args.candidate and any((args.release, args.tag_object, args.commit)):
            raise ProvisionError('--candidate cannot be combined with consumer release proof')
        identity = source_identity(args)
        project = args.project.resolve()
        if not project.is_dir():
            raise ProvisionError('destination project must already exist')
        edition = args.source.resolve() / 'v0.5'
        manifest, packages, registry = bundle.load(edition)
        identity['bundle_sha256'] = bundle.digest((edition / bundle.BUNDLE / 'integrity.json').read_bytes())
        if args.action == 'discover':
            if args.skill is not None:
                raise ProvisionError('--skill is only valid with retain or fallback')
            report = discover_local(project, identity, manifest, packages, registry, edition, args.custom_bindings_dir)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        for parent in (project / '.agents', project / '.agents/skills',
                       project / '.agents/.skill-provisioning'):
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise ProvisionError(f'{parent.name}: symbolic link or non-directory parent; reconcile it explicitly')
        if args.action == 'retain':
            if args.skill not in packages:
                raise ProvisionError('retain requires --skill naming one selected inventory skill')
            history.retain(project, args.skill, identity, registry.skills[args.skill], packages[args.skill]['LICENSE'])
        elif args.skill is not None and args.action != 'fallback':
            raise ProvisionError('--skill is only valid with retain or fallback')
        report = inspect(project, identity, manifest, packages, registry, edition)
        inspection = (project, identity, manifest, packages, registry, edition)
        if args.action == 'fallback':
            row = next((s for s in report['skills'] if s['name'] == args.skill), None)
            if row is None or not row['fallback']:
                raise ProvisionError('fallback requires --skill with an existing stage-owned manual fallback')
            report['fallback_selection'] = {'skill': args.skill, 'route': row['fallback'],
                                            'scope': 'this report only; execution remains stage-owned'}
        conflicts = [s['name'] for s in report['skills'] if s['installation'] == 'conflict']
        if args.action == 'install':
            # Isolate only skills never installed here. A later edit to an installed
            # skill keeps that installation and its recovery history unchanged.
            recorded = (history.load(project)['current'] or {}).get('skills', {})
            later = [name for name in conflicts if recorded.get(name) is not None]
            if later:
                raise ProvisionError('conflicting project content: ' + ', '.join(later))
        if args.action in ('install', 'recover'):
            state = history.load(project)
            if args.action == 'recover':
                tx = state['transaction']
                # Resume recovery toward its saved destination; an interrupted
                # install is instead rolled back to its starting inventory.
                previous = (tx['after'] if tx['action'] == 'recover' else tx['before']) if tx else state['previous']
                if previous is None:
                    raise ProvisionError('no previous installation recorded; rerun install to finish missing skills')
                after = {'source': previous['source'], 'skills': dict(previous['skills'])}
            else:
                retained = history.retained(project)
                after = {'source': identity, 'skills': {n: history.encode(c) for n, c in packages.items()
                                                       if n not in conflicts}}
                # Installing in the candidate checkout itself makes Git dirty.
                # Keep the prior installation's source observation when only
                # that volatile flag changed; report current dirt independently.
                previous_source = (state['current'] or {}).get('source', {})
                if (args.candidate and project == args.source.resolve()
                        and {k: v for k, v in previous_source.items() if k != 'dirty'}
                        == {k: v for k, v in identity.items() if k != 'dirty'}):
                    after['source'] = previous_source
            retained = history.retained(project)
            for name in retained['skills']:
                if name not in registry.skills:
                    raise ProvisionError(f'{name}: retained skill absent from registry; preserve it and explicitly reconcile inventory changes')
                if args.action == 'install' and name in conflicts:
                    continue
                license_bytes = next(iter(packages.values()))['LICENSE']
                material = history.retained_content(project, name, retained, registry.skills[name], license_bytes)
                after['skills'][name] = history.encode(material)
            if state['transaction'] or args.action == 'recover' or not report['complete'] or history.present(state['current']) != history.present(after):
                changed = history.apply(project, state, args.action, after,
                                        withheld=conflicts if args.action == 'install' else ())
                report = {**inspect(project, identity, manifest, packages, registry, edition), 'changed': changed}
            if args.action == 'recover':
                report['recovery_complete'] = True
                report['recovered_source'] = after['source']
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2 if args.action in ('install', 'check') and not report['complete'] else 0
    except (ProvisionError, history.StateError, bundle.BundleError, upstream_registry.RegistryError,
            OSError, ValueError, KeyError) as error:
        if inspection is not None:
            try:
                report = {**inspect(*inspection), 'changed': report['changed']}
            except (OSError, ValueError, KeyError):
                pass  # Preserve the prior observation if the source is no longer readable.
        try:
            tx = history.load(project)['transaction'] if inspection else None
            if tx:
                report['changed'] = [n for n in sorted(tx['after']['skills'])
                                     if history.content(tx['before'], n) != history.content(tx['after'], n)
                                     and history.actual(project, n) == history.content(tx['after'], n)]
        except (OSError, ValueError, KeyError):
            pass
        report['complete'] = False
        report['error'] = str(error)
        report['repair'] = ('Restore verified bundle material if damaged. For later or unknown project edits, '
                            'commit and explicitly retain --skill NAME, or move conflicting files outside the skill directory '
                            'before retrying. For interrupted replacement, retry the identical install or select recover; '
                            'preserve malformed records for explicit reconciliation. ' + str(error))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2


if __name__ == '__main__':
    sys.exit(main())
