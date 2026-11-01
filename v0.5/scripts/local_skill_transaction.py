"""Journal local skill/base/state file changes without replacing user directories."""
from __future__ import annotations

import fcntl
import ctypes
import sys
import importlib.util
import os
from pathlib import Path
import stat

import provisioning_state as history
import skill_adoption
from local_skill_inventory import plan, read_regular


def pack(data):
    return history.encode({'bytes': data}) if data is not None else None


def unpack(value):
    if value is None:
        return None
    decoded = history.decode(value)
    if set(decoded) != {'bytes'}:
        raise ValueError('invalid local skill journal bytes')
    return decoded['bytes']


def validate_path(relative):
    history.validate_path(relative)
    if not (relative == '.playbook-state.yml' or relative.startswith('.agents/skills/')
            or relative.startswith('.playbook-base/.agents/skills/')):
        raise ValueError('local skill journal path is outside its owned scope')


def load(path):
    record = history.read_json(path, None)
    if record is None:
        return None
    if (not isinstance(record, dict) or set(record) != {'schema_version', 'source', 'direction', 'pending', 'observations', 'changes'}
            or record['schema_version'] != 1 or record['direction'] not in ('install', 'recover')
            or type(record['pending']) is not bool or not isinstance(record['source'], dict)
            or not isinstance(record['observations'], dict) or not isinstance(record['changes'], dict)):
        raise ValueError('invalid local skill journal; preserve and reconcile it')
    for relative, value in record['observations'].items():
        validate_path(relative)
        unpack(value)
    for relative, entry in record['changes'].items():
        validate_path(relative)
        if not isinstance(entry, dict) or set(entry) != {'before', 'after'}:
            raise ValueError('invalid local skill journal change')
        unpack(entry['before']); unpack(entry['after'])
        if record['observations'].get(relative) != entry['before']:
            raise ValueError('local skill journal observation mismatch')
    return record


def preflight(project, record):
    for relative, observed in record['observations'].items():
        current = read_regular(project, relative)
        allowed = [unpack(observed)]
        if relative in record['changes']:
            allowed.append(unpack(record['changes'][relative]['after']))
            validate_staged(project, relative, allowed)
        if current not in allowed:
            raise ValueError(f'{relative}: changed during local skill operation; preserve and reconcile it')


def staged_path(relative):
    path = Path(relative)
    return str(path.with_name('.playbook-write-' + path.name))


def atomic_move(source, target, *, exchange=False):
    """Swap while retaining displaced bytes, or publish only to an absent name."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = getattr(library, 'renamex_np', None)
        if rename is None:
            raise ValueError('atomic file publication is unavailable on this host')
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        args = [os.fsencode(source), os.fsencode(target), 2 if exchange else 4]
    elif sys.platform.startswith('linux'):
        rename = getattr(library, 'renameat2', None)
        if rename is None:
            raise ValueError('atomic file publication is unavailable on this host')
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        args = [-100, os.fsencode(source), -100, os.fsencode(target), 2 if exchange else 1]
    else:
        raise ValueError('local skill publication requires Linux or macOS atomic rename support')
    rename.restype = ctypes.c_int
    if rename(*args):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def validate_staged(project, relative, values):
    staged = staged_path(relative)
    material = read_regular(project, staged)
    if material is not None and material not in [value for value in values if value is not None]:
        raise ValueError(f'{staged}: unknown displaced or staged bytes; preserve and reconcile them')
    return material


def write_file(project, relative, expected, desired, published=None):
    path = project / relative
    stage_relative = staged_path(relative)
    temporary = project / stage_relative
    if read_regular(project, relative) != expected:
        raise ValueError(f'{relative}: concurrent edit; preserve it and retry after reconciliation')
    if desired is None:
        atomic_move(path, temporary)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = stat.S_IMODE(path.stat().st_mode) if expected is not None else 0o644
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        with os.fdopen(fd, 'wb') as out:
            os.fchmod(out.fileno(), mode)
            out.write(desired)
            out.flush(); os.fsync(out.fileno())
        if read_regular(project, relative) != expected:
            raise ValueError(f'{relative}: concurrent edit; preserve it and reconcile')
        atomic_move(temporary, path, exchange=expected is not None)
    if published is not None:
        published.add(relative)
    if expected is not None:
        displaced = read_regular(project, stage_relative)
        if displaced != expected:
            # A writer won after validation. Its bytes survived the atomic move.
            # Restore them only while our published value is still at the target.
            if read_regular(project, relative) == desired:
                if desired is None:
                    atomic_move(temporary, path)
                else:
                    atomic_move(temporary, path, exchange=True)
                    if read_regular(project, stage_relative) == desired:
                        temporary.unlink()
            raise ValueError(f'{relative}: concurrent edit at publication; preserved target/displaced bytes at {stage_relative}; reconcile before retry')
        temporary.unlink()


def provision(project, source, identity, action):
    report = {'scope': 'playbook-local-skills', 'complete': False, 'changed': [], 'skills': [],
              'discovery': 'unverified', 'qualification': 'unverified', 'transaction_pending': False}
    descriptor = None
    observed = {}
    published = set()
    folder = project / '.playbook/local-skill-history'
    path = folder / 'operation.json'
    try:
        # Direct repair has the same adoption boundary as the startup wrapper.
        # A valid release supplied by the caller is not itself an upgrade choice.
        read_regular(project, '.playbook-state.yml')
        spec = importlib.util.spec_from_file_location('local_source_recovery',
                                                     Path(__file__).with_name('recover-playbook-source.py'))
        recovery = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(recovery)
        proof = recovery.adopted_proof(project)
        if identity.get('kind') != 'verified-release' or tuple(identity.get(k) for k in ('release', 'tag_object', 'commit')) != proof:
            raise ValueError('local skill repair requires the exact adopted release; explicitly upgrade before changing it')
        record = skill_adoption.setup_record(project)
        skill_adoption.validate_setup_inventory(project, source, proof, record)
        # Validate every ancestor through the same regular-file reader.
        record = load(path) if read_regular(project, str(path.relative_to(project))) is not None else None
        if action in ('install', 'recover'):
            folder.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(folder / 'operation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('local skill lock must be a regular private file')
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            record = load(path)
        bound = {'identity': {k: v for k, v in identity.items() if k not in ('proof', 'dirty')},
                 'path': str(source)}
        if record and (record['pending'] or action == 'recover'):
            if record['source'] != bound:
                raise ValueError('local skill recovery requires its exact recorded source and location')
            if action == 'check':
                report['transaction_pending'] = True
                raise ValueError('local skill transaction is pending; retry identical install or recover-local')
            if action == 'install' and record['direction'] != 'install':
                raise ValueError('finish the pending local skill recovery before installing')
            preflight(project, record)
        elif action == 'recover':
            raise ValueError('no local skill operation is recorded')
        else:
            prepared = plan(project, source)
            report['skills'] = prepared['skills']
            if prepared['errors']:
                raise ValueError('; '.join(prepared['errors']))
            if not prepared['changes']:
                report['complete'] = True
                return report
            if action == 'check':
                report['repair'] = 'Run install-local to restore managed support and relocate source references.'
                return report
            for relative in prepared['changes']:
                if read_regular(project, staged_path(relative)) is not None:
                    raise ValueError(f'{staged_path(relative)}: pre-existing staging file; preserve and reconcile it')
            record = {'schema_version': 1, 'source': bound, 'direction': 'install', 'pending': True,
                      'observations': {p: pack(data) for p,data in prepared['observations'].items()},
                      'changes': {p: {k: pack(v) for k,v in entry.items()} for p,entry in prepared['changes'].items()}}
        record = {**record, 'direction': action, 'pending': True}
        preflight(project, record)
        observed = {p: read_regular(project, p) for p in record['changes']}
        history.write_json(path, record)
        for relative in sorted(record['changes'], key=lambda p: (p == '.playbook-state.yml', p)):
            preflight(project, record)
            desired = unpack(record['changes'][relative]['before' if action == 'recover' else 'after'])
            current = read_regular(project, relative)
            allowed = [unpack(record['changes'][relative][side]) for side in ('before', 'after')]
            if current not in allowed:
                raise ValueError(f'{relative}: concurrent edit after validation; preserve it and reconcile')
            staged = validate_staged(project, relative, allowed)
            if staged is not None:
                (project / staged_path(relative)).unlink()
            if current != desired:
                write_file(project, relative, current, desired, published)
        preflight(project, record)
        history.write_json(path, {**record, 'pending': False})
        if action == 'recover':
            report['recovery_complete'] = True
        prepared = plan(project, source)
        report['skills'] = prepared['skills']
        report['complete'] = not prepared['errors'] and not prepared['changes']
        if prepared['errors']:
            report['repair'] = '; '.join(prepared['errors'])
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        report['error'] = str(error)
        report['repair'] = 'Preserve edits and journal evidence; retry the identical source or recover-local. ' + str(error)
    finally:
        for relative, before in observed.items():
            try:
                if read_regular(project, relative) != before:
                    report['changed'].append(relative)
            except (OSError, ValueError) as error:
                if relative in published:
                    report['changed'].append(relative)
                report.setdefault('observation_errors', {})[relative] = str(error)
        try:
            latest = load(path)
            report['transaction_pending'] = bool(latest and latest['pending'])
        except (OSError, ValueError) as error:
            report['transaction_pending'] = True
            report['error'] = str(error)
        if descriptor is not None:
            os.close(descriptor)
        settled = not report.get('error') and not report['transaction_pending'] and not report.get('observation_errors')
        report['complete'] = report['complete'] and settled
        if report.get('recovery_complete'):
            report['recovery_complete'] = settled
    return report
