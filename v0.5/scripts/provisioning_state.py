"""Project-local installation history; file evidence never grants runtime authority."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

import upstream_bundle as bundle


class StateError(ValueError):
    """Preserve the workspace until installation evidence is reconciled."""


def root(project):
    return project / '.agents/.skill-provisioning'


def safe_file(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise StateError(f'{path.name}: expected a regular provisioning record; reconcile it explicitly')


def read_json(path, default):
    safe_file(path)
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, value):
    safe_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='record-', delete=False) as f:
        temporary = Path(f.name)
        f.write((json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def encode(content):
    if content is None:
        return None
    files = {p: base64.b64encode(b).decode('ascii') for p, b in content.items()}
    checksum = bundle.digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
    return {'files': files, 'sha256': checksum}


def validate_path(name):
    p = PurePosixPath(name)
    if (not isinstance(name, str) or not p.parts or p.is_absolute() or '..' in p.parts
            or p.as_posix() != name or '\\' in name or '\x00' in name):
        raise StateError('unsafe installation content path')


def decode(value):
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'files', 'sha256'}
            or not isinstance(value['files'], dict)):
        raise StateError('invalid installation content record')
    files = value['files']
    checksum = bundle.digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
    if value['sha256'] != checksum:
        raise StateError('saved installation integrity mismatch; preserve history for explicit reconciliation')
    result = {}
    for name, data in files.items():
        validate_path(name)
        if not isinstance(data, str):
            raise StateError('invalid installation bytes')
        try:
            result[name] = base64.b64decode(data, validate=True)
        except ValueError as error:
            raise StateError('invalid installation bytes') from error
    for name in result:
        if any(parent.as_posix() in result for parent in PurePosixPath(name).parents):
            raise StateError('overlapping installation paths')
    return result


def validate_inventory(value):
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {'source', 'skills'}:
        raise StateError('invalid installation inventory')
    if not isinstance(value['source'], dict) or not isinstance(value['skills'], dict):
        raise StateError('invalid installation inventory')
    for name, content in value['skills'].items():
        if not re.fullmatch('[a-z][a-z0-9-]*', name):
            raise StateError('unsafe installation skill name')
        decode(content)


def load(project):
    state = read_json(root(project) / 'state.json',
                      {'schema_version': 1, 'current': None, 'previous': None, 'transaction': None})
    if not isinstance(state, dict) or set(state) != {'schema_version', 'current', 'previous', 'transaction'} or state['schema_version'] != 1:
        raise StateError('invalid installation history; preserve state.json for explicit reconciliation')
    validate_inventory(state['current'])
    validate_inventory(state['previous'])
    tx = state['transaction']
    if tx is not None:
        if not isinstance(tx, dict) or set(tx) != {'action', 'before', 'after'} or not isinstance(tx['action'], str) or tx['action'] not in {'install', 'recover'}:
            raise StateError('invalid interrupted transaction')
        validate_inventory(tx['before'])
        validate_inventory(tx['after'])
        if tx['after'] is None or tx['before'] is None:
            raise StateError('missing transaction inventory')
    return state


def actual(project, name):
    path = project / '.agents/skills' / name
    if not path.exists() and not path.is_symlink():
        return None
    return bundle.files(path)


def content(inventory, name):
    return decode(inventory['skills'].get(name)) if inventory else None


def capture(project, names, source):
    return {'source': source, 'skills': {name: encode(actual(project, name)) for name in sorted(names)}}


def save(project, state):
    write_json(root(project) / 'state.json', state)


def apply(project, state, action, after):
    """Journal before activation; only replace bytes matching observed history."""
    tx = state['transaction']
    if tx is not None:
        if action == 'install' and (tx['action'] != action or tx['after'] != after):
            raise StateError('interrupted replacement: retry the identical install or select recover first')
        before = tx['before']
    else:
        names = set(after['skills']) | set((state['current'] or {}).get('skills', {}))
        before = capture(project, names, (state['current'] or {}).get('source', {}))
    names = sorted(set(before['skills']) | set(after['skills']))
    # Validate staging ancestors even when activation already finished and only
    # journal finalization/backup cleanup remains after an interruption.
    staging = root(project) / 'work'
    for path in [staging, *(staging / name for name in names)]:
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise StateError('unsafe staging directory; preserve it for explicit reconciliation')
    # Observe every affected directory before any replacement. Later edits block.
    for name in names:
        current = actual(project, name)
        allowed = [content(before if tx else state['current'], name), content(after, name)]
        if tx:
            allowed.append(content(tx['after'], name))
        # A directory temporarily renamed away is recoverable only with its backup.
        backup = root(project) / 'work' / name / 'previous'
        if tx and current is None and backup.exists():
            # Retrying rollback of a pending install may find its newly
            # activated bytes renamed aside by the interrupted recovery.
            if bundle.files(backup) in [content(before, name), content(tx['after'], name)]:
                allowed.append(None)
        if current not in allowed:
            raise StateError(f'{name}: later or unknown edits; commit and retain them, or move them outside the skill directory before retrying {action}')
    if tx is None and state['current'] == after:
        return []
    if not tx:
        state['transaction'] = {'action': action, 'before': before, 'after': after}
        save(project, state)
    changed = []
    for name in names:
        desired = content(after, name)
        current = actual(project, name)
        if current == desired:
            continue
        work = root(project) / 'work'
        if work.is_symlink() or (work.exists() and not work.is_dir()):
            raise StateError('work: unsafe staging directory; reconcile it explicitly')
        folder = work / name
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise StateError(f'{name}: unsafe staging directory; reconcile it explicitly')
        folder.mkdir(parents=True, exist_ok=True)
        staged = folder / 'next'
        backup = folder / 'previous'
        for p in (staged, backup):
            if p.is_symlink():
                raise StateError(f'{name}: symbolic link in staging; reconcile it explicitly')
        if staged.exists():
            # Keep unexpected evidence; only discard a complete known staged copy.
            if bundle.files(staged) not in [desired, content(tx['after'], name) if tx else desired]:
                raise StateError(f'{name}: unknown staged material; move work/{name}/next aside before retrying')
            shutil.rmtree(staged)
        if desired is not None:
            staged.mkdir()
            for relative, data in desired.items():
                path = staged / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        target = project / '.agents/skills' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if actual(project, name) != current:
            raise StateError(f'{name}: source changed during staging; preserve edits and retry after reconciliation')
        if current is not None:
            if backup.exists():
                if bundle.files(backup) != content(before, name):
                    raise StateError(f'{name}: unknown backup material; preserve it for explicit reconciliation')
                shutil.rmtree(backup)
            os.rename(target, backup)
        if desired is not None:
            os.rename(staged, target)
        changed.append(name)
    # Remove only backups whose bytes are still the journal's observed previous copy.
    for name in names:
        backup = root(project) / 'work' / name / 'previous'
        if backup.exists():
            if bundle.files(backup) not in [content(before, name), content(after, name), content(tx['after'], name) if tx else None]:
                raise StateError(f'{name}: changed backup material; preserve it for reconciliation')
            shutil.rmtree(backup)
    state['current'] = after
    state['previous'] = before if action == 'install' else after
    state['transaction'] = None
    save(project, state)
    # History contains recovery bytes; obsolete staging is not a discovery source.
    return changed


def retained(project):
    record = read_json(root(project) / 'retained.json', {'schema_version': 1, 'skills': {}})
    if (not isinstance(record, dict) or set(record) != {'schema_version', 'skills'}
            or record['schema_version'] != 1 or not isinstance(record['skills'], dict)):
        raise StateError('invalid retained customization record')
    for name, entry in record['skills'].items():
        if not re.fullmatch('[a-z][a-z0-9-]*', name) or not isinstance(entry, dict) or set(entry) != {'integrity', 'based_on'}:
            raise StateError('invalid retained customization entry')
        if not isinstance(entry['based_on'], dict) or not isinstance(entry['integrity'], dict):
            raise StateError('invalid retained customization provenance')
        for path, digest in entry['integrity'].items():
            validate_path(path)
            if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                raise StateError('invalid retained customization hash')
    return record


def require_committed(project, name, material):
    import subprocess
    def git(*args):
        return subprocess.run(['git', '-C', str(project), *args], capture_output=True)
    top = git('rev-parse', '--show-toplevel')
    if top.returncode or Path(os.fsdecode(top.stdout).strip()).resolve() != project:
        raise StateError(f'{name}: retention requires committed files in this project Git root')
    prefix = f'.agents/skills/{name}/'
    listed = git('ls-tree', '-rz', '--full-tree', 'HEAD', '--', prefix)
    committed = {}
    for entry in listed.stdout.split(b'\x00'):
        if not entry:
            continue
        info, path = entry.split(b'\t', 1)
        mode, kind, oid = info.split()
        if mode not in (b'100644', b'100755') or kind != b'blob':
            raise StateError(f'{name}: committed customization must contain regular files')
        blob = git('cat-file', 'blob', oid.decode())
        if blob.returncode:
            raise StateError(f'{name}: committed customization is unreadable')
        committed[os.fsdecode(path)[len(prefix):]] = blob.stdout
    if listed.returncode or not material or committed != material:
        raise StateError(f'{name}: retention requires committed customized files; commit them first, then explicitly retain; untracked or later edits are preserved')


def retained_content(project, name, record, skill, license_bytes):
    entry = record['skills'].get(name)
    if entry is None:
        return None
    material = actual(project, name)
    if material is None or {p: bundle.digest(b) for p, b in material.items()} != entry['integrity']:
        raise StateError(f'{name}: retained source changed; commit and explicitly retain again, or restore its recorded bytes')
    require_committed(project, name, material)
    bundle.metadata(skill, material)
    if material.get('LICENSE') != license_bytes:
        raise StateError(f'{name}: preserve the unchanged upstream LICENSE before retaining')
    return material


def retain(project, name, identity, skill, license_bytes):
    if load(project)['transaction']:
        raise StateError('finish or recover the interrupted installation before retaining changes')
    material = actual(project, name)
    require_committed(project, name, material)
    bundle.metadata(skill, material)
    if material.get('LICENSE') != license_bytes:
        raise StateError(f'{name}: preserve the unchanged upstream LICENSE before retaining')
    record = retained(project)
    entry = {'integrity': {p: bundle.digest(b) for p, b in material.items()}, 'based_on': identity}
    if record['skills'].get(name) != entry:
        record['skills'][name] = entry
        write_json(root(project) / 'retained.json', record)
