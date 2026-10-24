#!/usr/bin/env python3
"""Maintainer command: package the registry selection from its reviewed Git source."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

import release_provenance as provenance
import upstream_bundle as bundle
import upstream_registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, help='clean checkout at the registry pin')
    parser.add_argument('--check', action='store_true', help='offline integrity and registry check')
    args = parser.parse_args(argv)
    edition = Path(__file__).resolve().parents[1]
    try:
        if args.check:
            manifest, _, _ = bundle.load(edition)
            print(f"Bundle verified: {len(manifest['skills'])} skills; {len(manifest['files'])} files.")
            return 0
        if args.upstream is None:
            parser.error('--upstream is required when generating')
        upstream = args.upstream.resolve()
        registry = upstream_registry.load(edition / 'upstream-skills.json')
        package = registry.packages[bundle.PACKAGE]
        tag = 'refs/tags/' + package.pin['value']
        if (provenance.git_output(upstream, 'status', '--porcelain', '--untracked-files=all') != ''
                or provenance.git_output(upstream, 'rev-parse', 'HEAD') != package.pin['commit']
                or provenance.git_output(upstream, 'cat-file', '-t', tag) != 'tag'
                or provenance.git_output(upstream, 'rev-parse', tag + '^{}') != package.pin['commit']):
            raise bundle.BundleError('upstream must be clean at the registry commit and annotated tag')
        tag_object = provenance.git_output(upstream, 'rev-parse', tag)
        material = {'LICENSE': (upstream / 'LICENSE').read_bytes()}
        for skill in bundle.selected(registry):
            for name, data in bundle.files(upstream / 'skills' / skill.upstream_path).items():
                material[f'{skill.name}/{name}'] = data
        manifest = bundle.record(registry, material, tag_object)
        destination = edition / bundle.BUNDLE
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
            staging = Path(tmp) / 'bundle'
            staging.mkdir()
            for name, data in material.items():
                path = staging / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (staging / 'integrity.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
            if destination.exists():
                raise bundle.BundleError('bundle already exists; review a replacement explicitly before regenerating')
            shutil.move(staging, destination)
        print(f'Bundled {len(manifest["skills"])} skills from {package.pin["value"]}.')
        return 0
    except (bundle.BundleError, upstream_registry.RegistryError, OSError) as error:
        print(f'Bundle rejected: {error}. Restore the reviewed source before retrying.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
