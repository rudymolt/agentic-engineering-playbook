"""S7 public discovery/Configure contracts, using synthetic official evidence."""

from copy import deepcopy
from datetime import datetime, timedelta
import unittest
import tempfile
from pathlib import Path
import json
import subprocess
import sys

import test_model_recommendations as fixtures
from playbook_config import Configuration
from model_recommendations import OfficialSources, SOURCES

NOW = fixtures.NOW


class RefreshTests(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover
    service = fixtures.RecommendationTests.service
    def test_discovery_reuses_inside_window_and_refreshes_after_window(self):
        now = [NOW]
        fetched = []
        service = self.service(sources=lambda: (fetched.append(now[0]) or deepcopy(self.evidence)))
        service.clock = lambda: now[0]
        first = service.read()
        now[0] = (datetime.fromisoformat(NOW.replace('Z', '+00:00')) + timedelta(hours=24, seconds=-1)).isoformat()
        service.read()
        self.assertEqual(len(fetched), 1)
        now[0] = (datetime.fromisoformat(NOW.replace('Z', '+00:00')) + timedelta(hours=24, seconds=1)).isoformat()
        service.read()
        self.assertEqual(len(fetched), 2)
        service.reply(first, 'Refresh')
        self.assertEqual(len(fetched), 3)

    def test_new_identity_checks_even_when_docs_unchanged_and_explain_does_not(self):
        fetched = []
        service = self.service(sources=lambda: (fetched.append(1) or deepcopy(self.evidence)))
        first = service.read()
        service.reply(first, 'Explain Build')
        self.assertEqual(len(fetched), 1)
        self.routes.append({**self.routes[0], 'model_id': 'new-version'})
        new = service.read()
        self.assertEqual(len(fetched), 2)
        self.assertEqual(new['recommendation_evidence']['changes'], [])
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_persistent_cache_failure_retains_success_and_changes_old_advice(self):
        with tempfile.TemporaryDirectory() as local:
            now = [NOW]
            failed = [False]
            calls = []
            def source():
                calls.append(1)
                if failed[0]:
                    raise OSError('private exception')
                evidence = deepcopy(self.evidence)
                for kind in ('guidance', 'rates'):
                    for record in evidence[kind]:
                        record['checked_at'] = now[0]
                return evidence
            def service():
                return Configuration(self.project, self.discover, lambda: now[0], context=self.context,
                                     recommendation_sources=source, evidence_dir=Path(local))
            first = service().read()
            self.assertTrue(first['recommendation_evidence']['cache_persisted'])
            second = service().read()
            self.assertEqual(len(calls), 1)
            self.evidence['guidance'][0]['text'] = 'Changed capability guidance for existing model'
            self.evidence['rates'][0]['input'] = 4
            now[0] = '2026-10-02T13:00:00Z'
            changed = service().read()['recommendation_evidence']
            self.assertEqual(len(changed['changes']), 2)
            self.assertTrue(all(item['checked_at'] == now[0] for item in changed['changes']))
            self.assertEqual(changed['rates'][0]['input'], 4)
            failed[0] = True
            now[0] = '2026-10-03T14:00:00Z'
            stale = service().read()['recommendation_evidence']
            self.assertEqual(stale['sources'][0]['checked_at'], '2026-10-02T13:00:00Z')
            self.assertEqual(stale['sources'][0]['status'], 'stale')
            self.assertEqual(stale['changes'], [])
            self.assertFalse((self.project / '.playbook-config.json').exists())
            self.assertEqual(self.state.read_bytes(), self.original)
            import json
            cached = json.loads(next(Path(local).glob('*.json')).read_text())
            self.assertNotIn('routes', cached)
            self.assertIn('discovery_fingerprint', cached)

    def test_official_sources_coalesce_and_fingerprint_unchanged_new_version(self):
        fetched = []
        html = '<p><a href="/api/docs/models/fixture-code">fixture-code</a> Recommended for coding.</p>'
        def fetch(url):
            fetched.append(url)
            return html if url == SOURCES[0] else '<p>Official guidance with no unambiguous rates</p>'
        service = self.service(sources=OfficialSources(lambda: NOW, fetch=fetch).retrieve)
        first = service.read()
        self.assertEqual(fetched, list(SOURCES))
        self.assertEqual(len(first['recommendation_evidence']['sources'][0]['content_fingerprint']), 64)
        fetched.clear()
        self.routes.append({**self.routes[0], 'model_id': 'new-version'})
        second = service.read()
        self.assertEqual(fetched, list(SOURCES))
        self.assertEqual(second['recommendation_evidence']['changes'], [])
        self.assertNotEqual(second['recommendations']['implementation']['choice']['model_id'], 'new-version')
        before = len(fetched)
        service.resolve('implementation')
        service.reply(second, 'Explain Build')
        service.reply(second, 'Not now')
        self.assertEqual(len(fetched), before)

    def test_lane_discovery_cache_and_explicit_feature_isolation(self):
        fetched = []
        context = {**self.context, 'constraints': {'implementation': {'authority': True, 'permission': True}}}
        service = self.service(context, sources=lambda: (fetched.append(1) or deepcopy(self.evidence)))
        feature = {'model_id': 'active-feature', 'runner': 'codex', 'reasoning': 'high'}
        first = service.advise('implementation', feature)
        second = service.advise('implementation', feature)
        self.assertEqual(len(fetched), 1)
        self.assertEqual(second['effective']['choice'], feature)
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_new_version_revision_with_changed_docs_reassesses_existing_models(self):
        service = self.service()
        first = service.read()
        self.evidence['guidance'][0]['text'] = 'Updated guidance for existing coding model'
        self.evidence['guidance'].append({**self.evidence['guidance'][0], 'model_id': 'new-version'})
        original_discover = service.discover
        service.discover = lambda request: {**original_discover(request), 'revision': 'new-version-revision',
                                           'routes': [*deepcopy(self.routes), {**self.routes[0], 'model_id': 'new-version'}]}
        second = service.read()
        self.assertEqual(len(second['recommendation_evidence']['changes']), 1)
        self.assertEqual(second['recommendations']['implementation']['guidance']['text'], 'Updated guidance for existing coding model')
        self.assertEqual(second['after'], first['after'])
        self.assertEqual(second['recommendation_evidence']['changes'][0]['source_url'], fixtures.GUIDANCE)

    def test_partial_official_failure_reuses_successful_sources_independently(self):
        fetched = []
        def fetch(url):
            fetched.append(url)
            if url == SOURCES[0]:
                return '<p><a href="/api/docs/models/fixture-code">fixture-code</a> Recommended for coding.</p>'
            if url == SOURCES[1]:
                return '<p>Reasoning controls</p>'
            raise OSError('outage')
        service = self.service(sources=OfficialSources(lambda: NOW, fetch=fetch).retrieve)
        service.read()
        fetched.clear()
        draft = service.read()
        self.assertEqual(fetched, list(SOURCES[2:]))
        self.assertIsNotNone(draft['recommendations']['implementation']['choice'])
        self.assertIsNone(draft['recommendations']['implementation']['cost']['rates'])
        self.assertEqual(draft['recommendation_evidence']['sources'][0]['checked_at'], NOW)

    def test_cli_cache_cross_request_and_new_model_outage_preserve_success_date(self):
        with tempfile.TemporaryDirectory() as private:
            fixture = Path(private) / 'evidence.json'
            fixture.write_text(json.dumps(self.evidence))
            cache = Path(private) / 'cache'
            def run(action, request, source=fixture):
                adapter = "import json,sys; r=json.load(sys.stdin); json.dump(dict(request_id=r['request_id'],checked_at=r['started_at'],authority='host-reported-selection',revision='fixture',routes=" + repr(self.routes) + "),sys.stdout)"
                command = [sys.executable, str(Path(__file__).with_name('configure-playbook.py')), action,
                           '--project', str(self.project), '--now', NOW, '--evidence-dir', str(cache),
                           '--evidence-fixture', str(source), '--discovery-command', json.dumps([sys.executable, '-c', adapter])]
                process = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
                self.assertEqual(process.returncode, 0, process.stderr)
                return json.loads(process.stdout)
            first = run('read', {'context': self.context})
            missing = Path(private) / 'unavailable.json'
            cached = run('read', {'context': self.context}, missing)
            self.assertEqual(cached['recommendations']['implementation']['choice']['model_id'], 'fixture-code')
            exit_result = run('reply', {'proposal': first, 'reply': 'Not now'}, missing)
            self.assertIn('advisory cache refreshed', exit_result['message'])
            self.routes.append({**self.routes[0], 'model_id': 'new-version'})
            failed = run('read', {'context': self.context}, missing)
            self.assertIsNone(failed['recommendations']['implementation']['choice'])
            self.assertEqual(failed['recommendation_evidence']['sources'][0]['checked_at'], NOW)
            self.assertEqual(failed['recommendation_evidence']['sources'][0]['status'], 'stale')
            self.assertEqual(self.state.read_bytes(), self.original)

    def test_cache_destination_retarget_into_project_refuses_persistence(self):
        with tempfile.TemporaryDirectory() as private:
            cache = Path(private) / 'cache'
            service = Configuration(self.project, self.discover, lambda: NOW, context=self.context,
                                    recommendation_sources=lambda: deepcopy(self.evidence), evidence_dir=cache)
            service.read()
            cache.rename(Path(private) / 'retained')
            cache.symlink_to(self.project, target_is_directory=True)
            refreshed = service.reply(service.read(), 'Refresh')
            self.assertFalse(refreshed['recommendation_evidence']['cache_persisted'])
            self.assertIn('persistence refused', refreshed['recommendation_evidence']['cache_limitations'])
            self.assertEqual(sorted(path.name for path in self.project.iterdir()), ['.playbook-state.yml'])


if __name__ == '__main__':
    unittest.main()
