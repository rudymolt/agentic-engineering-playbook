"""Bootstrap/upgrade-owned portable inventory choice; existing proof stays authority."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re

import release_provenance
import upstream_bundle
import conductor_setup as setup
from playbook_config import strict_json
from playbook_state import top_level_scalar_value, replace_top_level_scalar

KEY = 'skill_provisioning'
LAUNCHER = '.playbook/provision.pyz'
FIELDS = {'schema_version', 'bundle_sha256', 'launcher_sha256', 'launcher', 'local_policy'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_record(text):
    matches = re.findall(r'^' + KEY + r'[ \t]*:', text, re.M)
    if len(matches) > 1:
        raise ValueError('duplicate skill_provisioning adoption; restore the reviewed state record')
    raw = top_level_scalar_value(text, KEY)
    if not matches or raw in ('null', '~'):
        return None
    try:
        record = strict_json(raw or '')
    except ValueError:
        raise ValueError('invalid skill_provisioning adoption; restore its reviewed inline JSON record') from None
    if (not isinstance(record, dict) or set(record) != FIELDS
            or type(record.get('schema_version')) is not int or record['schema_version'] != 1
            or record.get('launcher') != LAUNCHER or record.get('local_policy') != 'discover'
            or any(not isinstance(record.get(k), str) or not re.fullmatch('[0-9a-f]{64}', record[k])
                   for k in ('bundle_sha256', 'launcher_sha256'))):
        raise ValueError('unsupported skill_provisioning adoption; preserve it and restore a compatible reviewed record')
    return record


def setup_record(project):
    """Require the prior inventory choice and its regular launcher before replay."""
    project = Path(project)
    state = project / '.playbook-state.yml'
    if not state.is_file():
        raise ValueError('setup requires readable adoption state; restore the recorded project state')
    record = read_record(state.read_text())
    if record is None:
        raise ValueError('setup requires explicit skill inventory adoption; preview bootstrap/upgrade '
                         '--adopt-skills and apply its reviewed --inventory-revision first')
    directory, launcher = project / '.playbook', project / LAUNCHER
    if directory.is_symlink() or launcher.is_symlink() or not launcher.is_file():
        raise ValueError('setup requires the regular adopted launcher; preserve linked or conflicting '
                         'endpoints and restore the reviewed .playbook/provision.pyz')
    if digest(launcher.read_bytes()) != record['launcher_sha256']:
        raise ValueError('adopted launcher integrity differs; preserve customizations and restore its '
                         'reviewed bytes or explicitly re-adopt through bootstrap/upgrade')
    return record


def validate_setup_inventory(project, source, proof, record):
    """Use the migration preview's existing source-derived inventory identity."""
    expected = prepare(project, source, proof)['summary']['record']
    if record != expected:
        raise ValueError('setup inventory or launcher differs from the exact adopted release; '
                         'restore the recorded release and launcher or explicitly re-adopt through '
                         'bootstrap/upgrade preview and Apply')


def require_writable_state(project):
    state = Path(project) / '.playbook-state.yml'
    if state.is_symlink():
        raise ValueError('linked adoption state cannot be written; preserve the link and target, '
                         'then explicitly restore a regular project .playbook-state.yml before Apply')
    if state.exists() and not state.is_file():
        raise ValueError('adoption state must be a readable regular file; preserve the endpoint and restore it')


def prepare(project, source, proof, *, for_apply=False, conductor_setup=False):
    project, source = Path(project).resolve(), Path(source).resolve()
    if project == source:
        raise ValueError('maintainer checkout cannot receive consumer adoption; use an isolated consumer fixture')
    if proof is None:
        raise ValueError('inventory adoption requires an exact verified public release; restore provenance or explicitly select a verified release')
    if for_apply:
        require_writable_state(project)
    manifest, packages, _ = upstream_bundle.load(source / 'v0.5')
    helper = source / 'v0.5/scripts/recover-playbook-source.py'
    if helper.is_symlink() or not helper.is_file():
        raise ValueError('release lacks its regular portable launcher; explicitly upgrade to a compatible reviewed release')
    spec = importlib.util.spec_from_file_location('adoption_source_recovery', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, 'launcher_bytes', None)):
        raise ValueError('release lacks the compatible launcher export interface; explicitly upgrade to a reviewed release')
    material = module.launcher_bytes()
    record = {'schema_version': 1, 'bundle_sha256': digest((source / 'v0.5' / upstream_bundle.BUNDLE / 'integrity.json').read_bytes()),
              'launcher_sha256': digest(material), 'launcher': LAUNCHER, 'local_policy': 'discover'}
    state = project / '.playbook-state.yml'
    if state.exists() or state.is_symlink():
        if not state.is_file():
            raise ValueError('adoption state must be a readable regular file; preserve the endpoint and restore it')
        state_before = state.read_text()
        previous = read_record(state_before)
    else:
        state_before = None
        previous = None
    directory = project / '.playbook'
    target = project / LAUNCHER
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError('preserve conflicting .playbook endpoint and restore a regular project directory')
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError('preserve nonregular or linked adoption launcher; restore its recorded regular bytes')
    current = None
    if target.exists():
        current = target.read_bytes()
        if current != material and (previous is None or digest(current) != previous['launcher_sha256']):
            raise ValueError('preserve customized adoption launcher; restore recorded bytes or move it aside explicitly')
    summary = {'source': dict(zip(('release', 'tag_object', 'commit'), proof)),
               'inventory': sorted(packages), 'record': record, 'local_policy': 'discover',
               'customizations': 'Preserve project and newer local sources; no local bundle activation. Commit and explicitly retain edits before replay.',
               'recovery': 'Replay through the exact adopted release; previous installation recovery and stage-owned fallback remain explicit.',
               'qualification': 'unverified'}
    setup_plan = setup.prepare(project, source, previous, current) if conductor_setup else None
    if setup_plan is None:
        setup_plan = setup.refresh(project, source, previous, current)
        if setup_plan is not None:
            summary['conductor_hook_refresh'] = {setup.SCRIPT: {name: digest(value) for name, value in
                                                 (('before_sha256', setup_plan['files'][setup.SCRIPT]['before']),
                                                  ('after_sha256', setup_plan['files'][setup.SCRIPT]['after']))}}
    elif setup_plan is not None:
        summary['conductor_setup'] = {'setup_after': setup_plan['setup'], 'files': {name: {'before_sha256': digest(v['before']) if v['before'] is not None else None, 'after_sha256': digest(v['after'])} for name, v in setup_plan['files'].items()}, 'cloud': 'explicit exact adopted release acquisition to separate cache; no upgrades', 'local': 'discovery only; no acquisition or aliases', 'activation': 'Cloud creation branch; local remote default branch; overrides may mask shared setup'}
    summary['inventory_revision'] = digest(json.dumps(summary, sort_keys=True).encode())
    return {'summary': summary, 'material': material, 'state_before': state_before,
            'launcher_before': current, 'setup_plan': setup_plan}


def require_revision(plan, revision):
    if revision != plan['summary']['inventory_revision']:
        raise ValueError('inventory approval is missing or changed; review the existing preview and pass its exact --inventory-revision with Apply')


def write_record(state, record):
    read_record(state)
    line = json.dumps(record, sort_keys=True)
    if re.search(r'^' + KEY + ':', state, re.M):
        return replace_top_level_scalar(state, KEY, line)
    for anchor in ('last_upgraded:', 'prereqs_required:'):
        if re.search(r'^' + anchor, state, re.M):
            return re.sub(r'^' + anchor, KEY + ': ' + line + '\n' + anchor, state, count=1, flags=re.M)
    raise ValueError('cannot place portable inventory adoption in customized state; restore its certification fields')


def apply(project, state, plan):
    require_writable_state(project)
    target = Path(project) / LAUNCHER
    changed = []
    if not target.exists() or target.read_bytes() != plan['material']:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(plan['material'])
        changed.append(str(target))
    if plan.get('setup_plan') is not None:
        changed.extend(setup.apply(Path(project), plan['setup_plan']))
    return write_record(state, plan['summary']['record']), changed


def rollback_certification(project, plan):
    """Keep safe migration edits, but never certify a failed adopted setup."""
    require_writable_state(project)
    if plan.get('setup_plan') is not None:
        setup.rollback(Path(project), plan['setup_plan'])
    state_path = Path(project) / '.playbook-state.yml'
    if state_path.is_file():
        state = state_path.read_text()
        before = plan['state_before']
        for key in ('playbook_version', 'playbook_release', 'playbook_release_tag_object',
                    'playbook_release_commit', 'last_upgraded', 'prereqs_required', KEY):
            pattern = r'^' + key + r':[^\n]*(?:\n|$)'
            old = re.search(pattern, before or '', re.M)
            if old:
                state = re.sub(pattern, lambda _: old.group(0), state, count=1, flags=re.M)
            elif before is None and key != KEY:
                state = replace_top_level_scalar(state, key, 'true' if key == 'prereqs_required' else 'null')
            else:
                state = re.sub(pattern, '', state, count=1, flags=re.M)
        if state != state_path.read_text():
            state_path.write_text(state)
    target = Path(project) / LAUNCHER
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError('preserve changed launcher endpoint and inspect incomplete adoption before retrying')
    if target.exists() and target.read_bytes() == plan['material']:
        previous = plan['launcher_before']
        if previous is None:
            target.unlink()
        elif previous != plan['material']:
            target.write_bytes(previous)


def print_plan(plan):
    print('Skill inventory adoption: ' + json.dumps(plan['summary'], sort_keys=True))
