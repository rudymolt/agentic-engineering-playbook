"""Coordinate existing per-host journals with one durable rollback destination."""
from __future__ import annotations

import provisioning_state as history


def load(path, hosts):
    value = history.read_json(path, None)
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'action', 'pending', 'before', 'after'}
            or value['schema_version'] != 1 or value['action'] not in ('install', 'recover')
            or type(value['pending']) is not bool):
        raise history.StateError('invalid host transaction; preserve it for explicit reconciliation')
    for field in ('before', 'after'):
        if not isinstance(value[field], dict) or set(value[field]) != set(hosts):
            raise history.StateError('host transaction inventory differs; preserve and reconcile it')
        for inventory in value[field].values():
            if inventory is None:
                raise history.StateError('missing host transaction inventory')
            history.validate_inventory(inventory)
    return value


def recovery_targets(path, hosts):
    record = load(path, hosts)
    if record is None:
        raise history.StateError('no coordinated host installation recorded; preserve existing skills and history')
    return record['after'] if record['action'] == 'recover' else record['before']


def apply(path, layouts, action, after, *, repair_missing=False):
    """Preflight every host, save all rollback targets, then reuse host journals.

    The group record survives host journal finalization. A host that has not begun
    an update therefore rolls back to its current inventory, not its older one.
    """
    record = load(path, layouts)
    states = {host: history.load(layout) for host, layout in layouts.items()}
    if record and record['pending'] and action == 'install':
        if record['action'] != action or record['after'] != after:
            raise history.StateError('interrupted host group: retry the identical install or recover first')
    for host, layout in layouts.items():
        history.apply(layout, states[host], action, after[host], repair_missing=repair_missing, dry_run=True)
    if record and record['action'] == action and record['after'] == after:
        operation = {**record, 'pending': True}
    else:
        before = {}
        unchanged = True
        for host, layout in layouts.items():
            state = states[host]
            names = set(after[host]['skills']) | set((state['current'] or {}).get('skills', {}))
            before[host] = history.capture(layout, names, (state['current'] or {}).get('source', {}))
            unchanged = unchanged and state['transaction'] is None and history.present(state['current']) == history.present(after[host]) and history.present(before[host]) == history.present(after[host])
        if unchanged and record and not record['pending'] and action == 'install':
            return {}
        operation = {'schema_version': 1, 'action': action, 'pending': True, 'before': before, 'after': after}
    history.write_json(path, operation)
    changed = {}
    for host, layout in layouts.items():
        changed[host] = history.apply(layout, states[host], action, after[host], repair_missing=repair_missing)
    history.write_json(path, {**operation, 'pending': False})
    return changed
