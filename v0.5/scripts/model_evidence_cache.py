"""Bounded, private advisory evidence. Never stores launch authority or routes."""

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile

from model_recommendations import SOURCES, OfficialSources, matches_reviewed_guidance, valid_claim, successful_date_status


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def instant(value):
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Evidence clock must include timezone')
    return date


def semantic_claims(entry):
    # Review identity binds reuse, but an unchanged statement is not new advice.
    return {kind: [{key: value for key, value in record.items() if key not in {'checked_at', 'retrieved_at'}
                   and (kind != 'guidance' or key not in {'entry_fingerprint', 'reviewed_at', 'uncertainty'})}
                   for record in entry.get(kind, []) if isinstance(record, dict)] for kind in ('guidance', 'rates')}


class EvidenceCache:
    def __init__(self, clock, path=None, project=None):
        self.clock = clock
        self.path = Path(path) if path else None
        self.project = Path(project) if project else None
        self.saved = {}
        self.unpersisted = False

    def _private(self):
        if self.path is None:
            return True
        try:
            return self.project is not None and not self.path.resolve().is_relative_to(self.project.resolve())
        except (OSError, RuntimeError):
            return False

    def _load(self):
        if self.path is None:
            return deepcopy(self.saved)
        if not self._private():
            return {}
        try:
            if self.path.is_symlink() or self.path.stat().st_size > 262144:
                return {}
            value = json.loads(self.path.read_text())
            if value.get('schema_version') != 1 or not isinstance(value.get('entries'), dict):
                return {}
            # Untrusted local data can only supply validated advisory claims.
            if set(value['entries']) - set(SOURCES):
                return {}
            if any(not isinstance(entry, dict) or not isinstance(entry.get('source'), dict)
                   or entry['source'].get('source_url') != url
                   or any(not isinstance(entry.get(kind, []), list) or len(entry.get(kind, [])) > 256 for kind in ('guidance', 'rates'))
                   for url, entry in value['entries'].items()):
                return {}
            return value
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def retrieve(self, source, discovery, force=False, urls=None):
        saved = self._latest_saved()
        entries = saved.get('entries', {})
        before_entries = deepcopy(entries)
        # Hash exact discovered identity/version metadata; do not save a catalogue.
        identities = sorted(fingerprint(route) for route in discovery['routes'])
        discovered = fingerprint({'identities': identities, 'revision': discovery['revision']})
        new = discovered != saved.get('discovery_fingerprint')
        now = instant(self.clock())
        due = []
        adapter = getattr(source, '__self__', None)
        official = isinstance(adapter, OfficialSources)
        reviewed = adapter.reviewed_entries() if official else None
        tracked = SOURCES if official or not entries else tuple(entries)
        if urls is not None:
            tracked = tuple(url for url in tracked if url in urls)
        for url in tracked:
            entry = entries.get(url, {})
            rejected = False
            if official:
                guidance = entry.get('guidance', [])
                matching = [record for record in guidance if matches_reviewed_guidance(record, reviewed)
                            and record.get('source_url') == url]
                rejected = len(matching) != len(guidance)
                if rejected:
                    entry['guidance'] = matching
            try:
                age = (now - instant(entry['source']['checked_at'])).total_seconds()
                fresh = (0 <= age <= 86400 and entry['source']['status'] == 'retrieved'
                         and all(valid_claim(record, kind, now=now)
                                 for kind in ('guidance', 'rates') for record in entry.get(kind, [])))
            except (KeyError, ValueError, TypeError, AttributeError):
                fresh = False
            if force or new or rejected or not fresh:
                due.append(url)
        fetched = {}
        if due and source is not None:
            try:
                adapter = getattr(source, '__self__', None)
                if isinstance(adapter, OfficialSources):
                    prior = {url: entry['source'] for url, entry in entries.items() if isinstance(entry, dict) and isinstance(entry.get('source'), dict)}
                    adapter.previous = prior
                    fetched = source(urls=due, retained_guidance=[claim for entry in entries.values() for claim in entry.get('guidance', [])])
                else:
                    fetched = source()
                if not isinstance(fetched, dict) or len(json.dumps(fetched, allow_nan=False)) > 262144:
                    raise ValueError('Unbounded evidence')
                if any(not isinstance(fetched.get(kind, []), list) or len(fetched.get(kind, [])) > 256
                       for kind in ('guidance', 'rates', 'sources')):
                    raise ValueError('Invalid evidence lists')
            except (OSError, ValueError, UnicodeError, TimeoutError, TypeError):
                fetched = {}
        # Live fetches stamp claims after the request starts; evaluate against
        # the actual post-fetch clock, never the earlier scheduling instant.
        now = instant(self.clock())
        changes = []
        refreshed = False
        result = {'guidance': [], 'rates': [], 'sources': [], 'changes': changes}
        if official:
            result['reviewed_models'] = [entry['model_id'] for entry in reviewed]
        for url in SOURCES:
            old = entries.get(url, {})
            if not isinstance(old, dict):
                old = {}
            current = deepcopy(old)
            if url in due:
                claims = {kind: [deepcopy(record) for record in fetched.get(kind, [])[:256]
                                 if valid_claim(record, kind, allow_unusable=True) and record.get('source_url') == url
                                 and (kind != 'guidance' or not official or matches_reviewed_guidance(record, reviewed))]
                          for kind in ('guidance', 'rates')}
                metadata = next((deepcopy(item) for item in fetched.get('sources', [])
                                 if isinstance(item, dict) and item.get('source_url') == url), {})
                metadata = {key: value for key, value in metadata.items() if key in {
                    'source_url', 'checked_at', 'retrieved_at', 'status', 'uncertainty', 'content_fingerprint', 'source_revision'}}
                usable = [record for kind, records in claims.items() for record in records
                          if valid_claim(record, kind, now=now)]
                if metadata.get('status') != 'retrieved' and usable:
                    metadata = {'source_url': url, 'checked_at': usable[0]['checked_at'],
                                'status': 'retrieved', 'uncertainty': 'Controlled structured evidence; no source revision available.'}
                try:
                    success = metadata.get('status') == 'retrieved' and 0 <= (now - instant(metadata['checked_at'])).total_seconds() <= 86400
                except (KeyError, ValueError, TypeError, AttributeError):
                    success = False
                if success:
                    metadata.setdefault('content_fingerprint', fingerprint(semantic_claims(claims)))
                    current = {**claims, 'source': metadata}
                    refreshed = True
                else:
                    prior = old.get('source', {})
                    retained_date = prior.get('checked_at')
                    uncertainty = ('Refresh incomplete; previous successful date retained. No fresh comparison.'
                                   if retained_date else 'Refresh incomplete; no successful check date is known. No fresh comparison.')
                    current = {**{kind: claims[kind] or old.get(kind, []) for kind in ('guidance', 'rates')},
                               'source': {**metadata, **prior, 'source_url': url, 'checked_at': retained_date,
                                               'status': 'stale' if retained_date else 'incomplete',
                                               'uncertainty': uncertainty}}
            if not current or (not official and not old and not any(claims.values()) and not metadata):
                continue
            previous = before_entries.get(url, {})
            before, after = semantic_claims(previous), semantic_claims(current)
            if previous.get('source', {}).get('checked_at') and before != after:
                changes.append({'source_url': url, 'checked_at': self.clock(),
                                'previous_checked_at': previous['source'].get('checked_at'),
                                'before': before, 'after': after,
                                'message': 'Official advice/cost evidence changed; reassess affected models. Defaults and approvals retained.'})
            entries[url] = current
            result['sources'].append(deepcopy(current['source']))
            for kind in ('guidance', 'rates'):
                for record in current.get(kind, [])[:256]:
                    if valid_claim(record, kind, allow_unusable=True):
                        item = deepcopy(record)
                        status = successful_date_status(item.get('checked_at'), now)
                        if status != 'retrieved':
                            item['status'] = status
                        elif current['source']['status'] != 'retrieved':
                            item['status'] = current['source']['status']
                        elif not valid_claim(item, kind, now=now):
                            # Keep the individual text/date for recovery, but a
                            # successful source or sibling cannot certify it.
                            if item.get('status') not in ('stale', 'incomplete', 'failed'):
                                item['status'] = 'incomplete'
                        result[kind].append(item)
        # A source-only acceptance check is not a complete discovery pass.
        self.saved = {'schema_version': 1, 'entries': entries,
                      'discovery_fingerprint': discovered if urls is None else saved.get('discovery_fingerprint')}
        result['cache_refreshed'] = refreshed
        result['cache_persisted'] = False
        if self.path and due and self._private():
            self.unpersisted = True
            data = json.dumps(self.saved, sort_keys=True, allow_nan=False)
            temporary_path = None
            try:
                if len(data.encode()) <= 262144:
                    self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as temporary:
                        temporary.write(data)
                        temporary_path = temporary.name
                    os.replace(temporary_path, self.path)
                    result['cache_persisted'] = True
                    self.unpersisted = False
            except OSError:
                result['cache_limitations'] = 'Local advisory cache could not be persisted; configuration unchanged.'
            finally:
                if temporary_path:
                    try:
                        Path(temporary_path).unlink(missing_ok=True)
                    except OSError:
                        pass
        elif self.path and not self._private():
            result['cache_limitations'] = 'Local advisory cache destination is no longer external; persistence refused.'
        return result

    def current_reviewed_entries(self, reviewed):
        """Local latest successful source state; never fetch or rerank retained advice."""
        entries = self._latest_saved().get('entries', {})
        current = []
        for entry in reviewed:
            source = entries.get(entry['source_url'], {})
            if not source.get('source', {}).get('checked_at') or any(
                    matches_reviewed_guidance(record, [entry]) for record in source.get('guidance', [])):
                current.append(entry)
        return current

    def _latest_saved(self):
        """A failed disk write must not undo a successful check in this instance."""
        saved = self._load()
        entries = saved.setdefault('entries', {})
        for url, local in self.saved.get('entries', {}).items() if self.unpersisted else ():
            try:
                local_date = instant(local['source']['checked_at'])
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            try:
                disk_date = instant(entries[url]['source']['checked_at'])
            except (KeyError, ValueError, TypeError, AttributeError):
                disk_date = None
            if disk_date is None or local_date >= disk_date:
                current = deepcopy(local)
                if local_date == disk_date:
                    # Equal timestamps cannot order two checks. A known
                    # withdrawal in either snapshot wins over confirmation.
                    confirmed = {record.get('entry_fingerprint') for record in entries[url].get('guidance', [])
                                 if isinstance(record, dict)}
                    current['guidance'] = [record for record in current.get('guidance', [])
                                           if record.get('entry_fingerprint') in confirmed]
                entries[url] = current
        return saved
