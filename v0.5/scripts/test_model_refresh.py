"""S7 public discovery/Configure contracts, using synthetic official evidence."""

from copy import deepcopy
from datetime import datetime, timedelta
from itertools import product
import unittest
import tempfile
from pathlib import Path
import json
import subprocess
import sys

import test_model_recommendations as fixtures
from playbook_config import Configuration
from model_recommendations import OfficialSources, SOURCES, cost, valid_claim, recommendations
from model_evidence_cache import EvidenceCache

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
        html = fixtures.REVIEWED_PAGE
        def fetch(url):
            fetched.append(url)
            return html if url == SOURCES[0] else '<p>Official guidance with no unambiguous rates</p>'
        service = self.service(sources=OfficialSources(lambda: NOW, fetch=fetch, reviewed=[fixtures.REVIEWED_CODE]).retrieve)
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
                return fixtures.REVIEWED_PAGE
            if url == SOURCES[1]:
                return '<p>Reasoning controls</p>'
            raise OSError('outage')
        service = self.service(sources=OfficialSources(lambda: NOW, fetch=fetch, reviewed=[fixtures.REVIEWED_CODE]).retrieve)
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


class ClaimFreshnessTests(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover
    clock = '2026-10-02T12:00:00+00:00'

    def dated_evidence(self, date, envelope=True):
        evidence = deepcopy(self.evidence)
        for kind in ('guidance', 'rates'):
            for record in evidence[kind]:
                record['checked_at'] = date
        if envelope:
            evidence['sources'] = [dict(source_url=url, checked_at=self.clock, status='retrieved')
                                   for url in (fixtures.GUIDANCE, fixtures.PRICING)]
        return evidence

    def test_cache_each_claim_date_is_independent_of_envelope_or_fresh_sibling(self):
        for date, status in (('2026-09-01T12:00:00+00:00', 'stale'),
                             ('2027-10-02T12:00:00+00:00', 'incomplete')):
            for envelope in (True, False):
                with self.subTest(date=date, envelope=envelope):
                    evidence = self.dated_evidence(date, envelope)
                    for kind in ('guidance', 'rates'):
                        evidence[kind].insert(0, {**evidence[kind][0], 'model_id': 'fresh-sibling',
                                                 'checked_at': self.clock})
                    cache = EvidenceCache(lambda: self.clock)
                    result = cache.retrieve(lambda: evidence, {'routes': self.routes, 'revision': 'fixture'})
                    for kind in ('guidance', 'rates'):
                        rejected = next(item for item in result[kind] if item['model_id'] == 'fixture-code')
                        self.assertEqual(rejected['checked_at'], date)
                        self.assertEqual(rejected.get('status'), status)
                        fresh = next(item for item in result[kind] if item['model_id'] == 'fresh-sibling')
                        self.assertNotIn(fresh.get('status'), ('stale', 'incomplete'))
                        self.assertFalse(valid_claim(rejected, kind))

    def test_cache_reuse_checks_claim_age_even_when_source_is_younger(self):
        now = [self.clock]
        evidence = self.dated_evidence('2026-10-01T12:00:00+00:00')
        calls = []
        def source():
            calls.append(1)
            if len(calls) > 1:
                raise OSError('outage')
            return evidence
        cache = EvidenceCache(lambda: now[0])
        discovery = {'routes': self.routes, 'revision': 'fixture'}
        first = cache.retrieve(source, discovery)
        self.assertNotIn(first['guidance'][0].get('status'), ('stale', 'incomplete'))
        now[0] = '2026-10-02T12:00:01+00:00'
        second = cache.retrieve(source, discovery)
        self.assertEqual(len(calls), 2)
        self.assertEqual(second['guidance'][0]['checked_at'], '2026-10-01T12:00:00+00:00')
        self.assertEqual(second['guidance'][0]['status'], 'stale')
        self.assertEqual(second['sources'][0]['checked_at'], self.clock)
        self.assertIsNone(cost(self.routes[0], self.context, second)['rates'])

    def test_first_failed_refresh_does_not_claim_a_prior_success(self):
        incomplete = {'guidance': [], 'rates': [], 'sources': [
            {'source_url': url, 'status': 'incomplete', 'checked_at': None}
            for url in SOURCES]}
        result = EvidenceCache(lambda: self.clock).retrieve(
            lambda: incomplete, {'routes': self.routes, 'revision': 'fixture'})
        self.assertEqual(len(result['sources']), len(SOURCES))
        for source in result['sources']:
            self.assertEqual(source['status'], 'incomplete')
            self.assertIsNone(source['checked_at'])
            self.assertIn('no successful check date is known', source['uncertainty'])
            self.assertNotIn('previous successful date retained', source['uncertainty'])

    def test_official_retrieval_evaluates_dates_after_fetch_completes(self):
        now = [self.clock]
        def fetch(url):
            now[0] = '2026-10-02T12:00:01+00:00'
            if url == SOURCES[0]:
                return fixtures.REVIEWED_PAGE
            return '<p>General official guidance</p>'
        cache = EvidenceCache(lambda: now[0])
        result = cache.retrieve(OfficialSources(lambda: now[0], fetch=fetch, reviewed=[fixtures.REVIEWED_CODE]).retrieve,
                                {'routes': self.routes, 'revision': 'fixture'})
        self.assertEqual(result['guidance'][0]['checked_at'], now[0])
        self.assertNotIn(result['guidance'][0].get('status'), ('stale', 'incomplete'))
        self.assertEqual(result['sources'][0]['checked_at'], now[0])

    def test_persisted_claims_expire_independently_and_missing_dates_stay_visible(self):
        with tempfile.TemporaryDirectory() as private:
            path = Path(private) / 'cache.json'
            now = [self.clock]
            evidence = self.dated_evidence('2026-10-01T12:00:00+00:00')
            evidence['guidance'].append({**evidence['guidance'][0], 'model_id': 'missing-date',
                                         'checked_at': None})
            discovery = {'routes': self.routes, 'revision': 'fixture'}
            first = EvidenceCache(lambda: now[0], path, self.project).retrieve(lambda: evidence, discovery)
            missing = next(item for item in first['guidance'] if item['model_id'] == 'missing-date')
            self.assertIsNone(missing['checked_at'])
            self.assertEqual(missing['status'], 'incomplete')
            now[0] = '2026-10-02T12:00:01+00:00'
            def outage():
                raise OSError('outage')
            reused = EvidenceCache(lambda: now[0], path, self.project).retrieve(outage, discovery)
            for kind in ('guidance', 'rates'):
                claim = next(item for item in reused[kind] if item['model_id'] == 'fixture-code')
                self.assertEqual(claim['checked_at'], '2026-10-01T12:00:00+00:00')
                self.assertEqual(claim['status'], 'stale')
            self.assertEqual(reused['sources'][0]['checked_at'], self.clock)
            self.assertIn('previous successful date retained', reused['sources'][0]['uncertainty'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_raw_advice_library_uses_clock_not_supplied_evaluation_metadata(self):
        for date in ('2026-09-01T12:00:00+00:00', '2027-10-02T12:00:00+00:00'):
            with self.subTest(date=date):
                evidence = self.dated_evidence(date)
                evidence['evaluated_at'] = date
                self.assertIsNone(cost(self.routes[0], self.context, evidence, now=self.clock)['rates'])
                advice = recommendations({'implementation': self.routes}, self.context, evidence,
                                         ['codex'], now=self.clock)
                self.assertIsNone(advice['implementation']['choice'])

    def test_claim_boundaries_and_exact_positive_date(self):
        for age, usable in ((1, True), (86399, True), (86400, True), (86401, False), (-1, False)):
            with self.subTest(age=age):
                date = (datetime.fromisoformat(self.clock) - timedelta(seconds=age)).isoformat()
                result = EvidenceCache(lambda: self.clock).retrieve(lambda: self.dated_evidence(date),
                          {'routes': self.routes, 'revision': 'fixture'})
                for kind in ('guidance', 'rates'):
                    self.assertEqual(result[kind][0]['checked_at'], date)
                    self.assertEqual(result[kind][0].get('status') not in ('stale', 'incomplete'), usable)
                if usable:
                    self.assertEqual(result['sources'][0]['checked_at'], self.clock)

    def cli_read(self, fixture, cache, now, context):
        adapter = "import json,sys; r=json.load(sys.stdin); json.dump(dict(request_id=r['request_id'],checked_at=r['started_at'],authority='host-reported-selection',revision='new-model',routes=" + repr(self.routes) + "),sys.stdout)"
        command = [sys.executable, str(Path(__file__).with_name('configure-playbook.py')), 'read',
                   '--project', str(self.project), '--now', now, '--evidence-dir', str(cache),
                   '--evidence-fixture', str(fixture),
                   '--discovery-command', json.dumps([sys.executable, '-c', adapter])]
        process = subprocess.run(command, input=json.dumps({'context': context}), text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertNotIn('Traceback', process.stdout + process.stderr)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(sorted(path.name for path in self.project.iterdir()), ['.playbook-state.yml'])
        return json.loads(process.stdout)

    def test_cli_invalid_guidance_withholds_replacement_and_invalid_rates_leave_cost_unknown(self):
        context = {**self.context, 'workload': dict(input_tokens=1000, output_tokens=500,
                    retries=2, billing_route='standard-short-context-uncached')}
        cases = (('2026-09-01T12:00:00+00:00', False), ('2027-10-02T12:00:00+00:00', False),
                 ('2026-10-02T11:59:59+00:00', True), ('2026-10-01T12:00:01+00:00', True),
                 ('2026-10-01T12:00:00+00:00', True), ('2026-10-01T11:59:59+00:00', False))
        for kind, (date, usable), envelope in product(('guidance', 'rates'), cases, (True, False)):
            with self.subTest(kind=kind, date=date, envelope=envelope), tempfile.TemporaryDirectory() as private:
                evidence = self.dated_evidence(self.clock, envelope)
                for record in evidence[kind]:
                    record['checked_at'] = date
                if not envelope:
                    # A current sibling establishes only its own successful date.
                    for category in ('guidance', 'rates'):
                        evidence[category].insert(0, {**evidence[category][0], 'model_id': 'undiscovered-sibling',
                                                     'checked_at': self.clock})
                fixture = Path(private) / 'source.json'
                fixture.write_text(json.dumps(evidence))
                result = self.cli_read(fixture, Path(private) / 'cache', self.clock, context)
                original = next(item for item in result['recommendation_evidence'][kind]
                                if item['model_id'] == 'fixture-code')
                self.assertEqual(original['checked_at'], date)
                advice = result['recommendations']['implementation']
                if kind == 'guidance' and not usable:
                    self.assertIsNone(advice['choice'])
                    self.assertIsNone(result['replacement']['advice']['choice'])
                    self.assertNotIn('Accept replacement', result['choices'])
                    self.assertIsNone(advice['cost'])
                else:
                    self.assertEqual(advice['choice']['model_id'], 'fixture-code')
                    usable_price = kind == 'guidance' or usable
                    self.assertEqual(advice['cost']['rates'] is not None, usable_price)
                    self.assertEqual(advice['cost']['estimate'] is not None, usable_price)

    def test_cli_persisted_claim_expires_under_still_fresh_source(self):
        with tempfile.TemporaryDirectory() as private:
            fixture = Path(private) / 'source.json'
            fixture.write_text(json.dumps(self.dated_evidence('2026-10-01T12:00:00+00:00')))
            cache = Path(private) / 'cache'
            first = self.cli_read(fixture, cache, self.clock, self.context)
            self.assertEqual(first['recommendations']['implementation']['choice']['model_id'], 'fixture-code')
            fixture.unlink()
            second = self.cli_read(fixture, cache, '2026-10-02T12:00:01+00:00', self.context)
            self.assertIsNone(second['recommendations']['implementation']['choice'])
            self.assertNotIn('Accept replacement', second['choices'])
            self.assertEqual(second['recommendation_evidence']['guidance'][0]['checked_at'],
                             '2026-10-01T12:00:00+00:00')
            self.assertEqual(second['recommendation_evidence']['guidance'][0]['status'], 'stale')
            self.assertEqual(second['recommendation_evidence']['sources'][0]['checked_at'], self.clock)


if __name__ == '__main__':
    unittest.main()
