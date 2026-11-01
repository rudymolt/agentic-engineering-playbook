"""Prepare complete local-skill repair and relocation using recorded ownership."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

import template_base
from playbook_config import strict_json


def read_regular(project, relative):
    path = project / relative
    for parent in [path.parent, *path.parent.parents]:
        if parent == project.parent:
            break
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(f'{relative}: linked or non-directory parent; preserve and reconcile it')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f'{relative}: expected an unlinked regular file; preserve its endpoint')
        return stream.read()


def plan(project, source):
    state_bytes = read_regular(project, '.playbook-state.yml')
    if state_bytes is None:
        raise ValueError('local skill repair requires recorded project adoption and template provenance')
    state = state_bytes.decode()
    provenance = template_base.read_provenance(state)
    if not provenance or not provenance.get('project_name'):
        raise ValueError('local skill repair requires recorded template bases and project name')
    # Enumerate the authenticated release inventory without probing readability.
    # Missing/unreadable templates must be errors, never a smaller required set.
    manifest = strict_json((source / 'v0.5/MANIFEST.json').read_bytes())
    mapping = {}
    for entry in manifest['files']:
        path = Path(entry['path'])
        if len(path.parts) >= 3 and path.parts[0] == 'skills' and path.parts[1] in template_base.MANAGED_SKILLS:
            mapping[str(Path('.agents') / path)] = str(Path('v0.5') / path)
    changes, observations, rows, errors = {}, {}, {}, []

    def observe(relative):
        data = read_regular(project, relative)
        observations[relative] = data
        return data

    for relative, template in mapping.items():
        name = Path(relative).parts[2]
        row = rows.setdefault(name, {'name': name, 'files': [], 'conflicts': [],
                                     'discovery': 'unverified', 'qualification': 'unverified'})
        try:
            entry = provenance['files'].get(relative)
            base_relative = str(Path(template_base.BASE_DIR) / relative)
            base = observe(base_relative)
            if (entry is None or entry.get('template') != template or base is None
                    or hashlib.sha256(base).hexdigest() != entry.get('base_sha256')):
                raise ValueError('missing or inconsistent template ownership; restore recorded provenance and pristine base')
            current = observe(relative)
            fresh = template_base.render((source / template).read_text(), source, provenance['project_name']).encode()
            if current is None:
                # A tracked customization is stronger recovery evidence than the pristine base.
                import subprocess
                top = subprocess.run(['git', '-C', str(project), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
                committed = None
                if top.returncode == 0 and Path(top.stdout.strip()).resolve() == project.resolve():
                    tree = subprocess.run(['git', '-C', str(project), 'ls-tree', '-z', 'HEAD', '--', relative], capture_output=True)
                    if tree.returncode:
                        raise ValueError('cannot inspect committed recovery material')
                    if tree.stdout:
                        mode = tree.stdout.split(b' ', 1)[0]
                        if mode not in (b'100644', b'100755'):
                            raise ValueError('committed recovery material is not a regular file; reconcile it explicitly')
                        saved = subprocess.run(['git', '-C', str(project), 'show', 'HEAD:' + relative], capture_output=True)
                        if saved.returncode:
                            raise ValueError('cannot read committed recovery material')
                        committed = saved.stdout
                ours = committed if committed is not None else base
            else:
                ours = current
            if ours == base:
                desired = fresh
            elif fresh == base:
                desired = ours
            else:
                merged, conflict = template_base.merge3(base.decode(), ours.decode(), fresh.decode())
                if conflict:
                    raise ValueError('source relocation conflicts with project customization; preserve and explicitly merge it')
                desired = merged.encode()
            if desired != current:
                changes[relative] = {'before': current, 'after': desired}
            if fresh != base:
                changes[base_relative] = {'before': base, 'after': fresh}
                provenance['files'][relative] = {**entry, 'base_sha256': hashlib.sha256(fresh).hexdigest()}
            row['files'].append({'path': relative, 'status': 'missing' if current is None else 'customized' if ours != base else 'managed'})
        except (OSError, ValueError, UnicodeError) as error:
            row['conflicts'].append(relative)
            errors.append(f'{relative}: {error}')
    # Preserve source header, adoption, routes and every unrelated state field.
    updated = template_base.upsert_provenance(state, provenance).encode()
    observations['.playbook-state.yml'] = state_bytes
    if updated != state_bytes:
        changes['.playbook-state.yml'] = {'before': state_bytes, 'after': updated}

    name = 'ai-playbook-deliver'
    row = rows.setdefault(name, {'name': name, 'files': [], 'conflicts': [],
                                 'discovery': 'unverified', 'qualification': 'unverified'})
    root = '.agents/skills/' + name
    try:
        if observe(root + '/install-state.json') is not None:
            raise ValueError('pending delivery lifecycle evidence; reconcile its existing operation before repair')
        spec = importlib.util.spec_from_file_location('local_delivery_lifecycle', source/'v0.5/delivery/scripts/lifecycle.py')
        lifecycle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lifecycle)
        manifest = lifecycle.source_manifest()
        lock_bytes = observe(root + '/manifest-lock.yml')
        if lock_bytes is None:
            raise ValueError('missing delivery ownership lock; restore the recorded installation')
        lock = strict_json(lock_bytes)
        if not isinstance(lock, dict):
            raise ValueError('delivery ownership lock must be an object')
        if lock.get('pack_digest') != manifest['pack_digest']:
            raise ValueError('delivery lock differs from adopted source; explicitly upgrade through its lifecycle')
        owned = lifecycle.validated_lock_owned_files(lock, expected=lifecycle.manifest_owned_files(manifest))
        entries = {e['install_path']: e for e in manifest['files'] if e.get('install_path') is not None}
        for relative, digest in owned.items():
            path = root + '/' + relative
            current = observe(path)
            if current is not None and 'sha256:' + hashlib.sha256(current).hexdigest() != digest:
                raise ValueError(f'{path}: modified delivery-owned content; preserve and reconcile it')
            if current is None:
                changes[path] = {'before': None, 'after': (source/'v0.5/delivery'/entries[relative]['source']).read_bytes()}
            row['files'].append({'path': path, 'status': 'missing' if current is None else 'managed'})
    except (OSError, ValueError, RuntimeError) as error:
        row['conflicts'].append(root)
        errors.append(f'{root}: {error}')
    return {'source': str(source), 'changes': changes, 'observations': observations,
            'skills': list(rows.values()), 'errors': errors}
