#!/usr/bin/env python3
"""Preview, install, or check the registry-selected project skill bundle.

Exit 0: successful preview/install/check; 2: incomplete check or blocked operation.
All commands emit JSON. Installation requires an explicit command and source proof.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

import release_provenance as provenance
import upstream_bundle as bundle
import upstream_registry


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


def inspect(project, identity, manifest, packages, registry, edition):
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
        try:
            actual = bundle.files(target)
            installed_integrity = {p: bundle.digest(b) for p, b in actual.items()}
        except (bundle.BundleError, OSError):
            installed_integrity = None
        rows.append({
            'name': name,
            'path': f'.agents/skills/{name}',
            'installation': status,
            'installed_source': manifest['commit'] if status == 'installed' else 'unknown',
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
    complete = all(s['installation'] == 'installed' for s in rows)
    return {'schema_version': 1, 'source': identity, 'skills': rows,
            'complete': complete, 'changed': [],
            'repair': None if complete else 'Rerun install to finish missing skills; preserve conflicts for explicit reconciliation.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='existing destination project')
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2],
                        help='available Playbook Git checkout; no acquisition is performed')
    parser.add_argument('--candidate', action='store_true', help='explicit maintainer testing; never a consumer release')
    parser.add_argument('--release', help='previously verified release tag')
    parser.add_argument('--tag-object', help='previously verified annotated tag object')
    parser.add_argument('--commit', help='previously verified release commit')
    parser.add_argument('action', choices=('preview', 'install', 'check'))
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
        for parent in (project / '.agents', project / '.agents/skills',
                       project / '.agents/.skill-provisioning'):
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise ProvisionError(f'{parent.name}: symbolic link or non-directory parent; reconcile it explicitly')
        report = inspect(project, identity, manifest, packages, registry, edition)
        inspection = (project, identity, manifest, packages, registry, edition)
        conflicts = [s['name'] for s in report['skills'] if s['installation'] == 'conflict']
        if args.action == 'install' and conflicts:
            raise ProvisionError('conflicting project content: ' + ', '.join(conflicts))
        if args.action == 'install' and not report['complete']:
            for name, content in packages.items():
                target = project / '.agents/skills' / name
                if installation_status(target, content) == 'installed':
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                # Staging lives outside runtime skill roots; activation is one rename.
                staging_root = project / '.agents/.skill-provisioning'
                staging_root.mkdir(exist_ok=True)
                with tempfile.TemporaryDirectory(dir=staging_root, prefix='initial-') as tmp:
                    staged = Path(tmp) / name
                    staged.mkdir()
                    for relative, data in content.items():
                        path = staged / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                    os.rename(staged, target)
                report['changed'].append(name)
            report = {**inspect(project, identity, manifest, packages, registry, edition), 'changed': report['changed']}
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2 if args.action == 'check' and not report['complete'] else 0
    except (ProvisionError, bundle.BundleError, upstream_registry.RegistryError,
            OSError, ValueError, KeyError) as error:
        if inspection is not None:
            try:
                report = {**inspect(*inspection), 'changed': report['changed']}
            except (OSError, ValueError, KeyError):
                pass  # Preserve the prior observation if the source is no longer readable.
        report['complete'] = False
        report['error'] = str(error)
        report['repair'] = 'Restore verified bundle material and retry; preserve conflicting project files for explicit reconciliation.'
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2


if __name__ == '__main__':
    sys.exit(main())
