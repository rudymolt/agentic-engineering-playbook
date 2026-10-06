"""S7 replacement conversation at the public Configure seam."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import test_model_recommendations as fixtures
from playbook_config import Configuration, ROLES


class ReplacementTests(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover
    service = fixtures.RecommendationTests.service

    def test_accept_is_draft_only_another_opens_editor_and_not_now_saves_nothing(self):
        service = self.service()
        initial = service.read()
        self.assertEqual(initial['step'], 'replacement')
        self.assertEqual(initial['replacement']['advice']['choice']['model_id'], 'fixture-code')
        role = initial['replacement']['role']
        accepted = service.reply(initial, 'Accept replacement')
        self.assertEqual(accepted['step'], 'preview')
        self.assertEqual(accepted['after'][role]['model_id'], 'fixture-code')
        self.assertEqual(accepted['before'], initial['before'])
        another = service.reply(initial, 'Choose another model')
        self.assertEqual(another['step'], 'edit')
        self.assertEqual(another['edit_role'], role)
        self.assertEqual(service.reply(initial, 'Not now')['state'], 'unchanged')
        self.assertFalse((self.project / '.playbook-config.json').exists())
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_no_suitable_alternative_is_visible_and_no_accept(self):
        self.evidence['guidance'] = []
        draft = self.service().read()
        self.assertIsNone(draft['replacement']['advice']['choice'])
        self.assertNotIn('Accept replacement', draft['choices'])
        self.assertIn('Choose another model', draft['choices'])

    def test_route_disappears_before_apply_invalidates_old_proposal(self):
        service = self.service()
        draft = service.read()
        for role in ROLES:
            draft = service.reply(draft, 'Edit ' + role)
            draft = service.reply(draft, '1')
        self.routes.pop(0)
        refreshed = service.reply(draft, 'Apply')
        self.assertEqual(refreshed['step'], 'replacement')
        self.assertEqual(refreshed['after'], draft['after'])
        self.assertIsNone(refreshed['replacement']['advice']['choice'])
        self.assertFalse((self.project / '.playbook-config.json').exists())
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_replacement_disappears_after_accept_and_file_changes_block(self):
        service = self.service()
        draft = service.reply(service.read(), 'Accept replacement')
        self.routes.pop(0)
        refreshed = service.reply(draft, 'Apply')
        self.assertEqual(refreshed['step'], 'replacement')
        self.assertEqual(refreshed['after'], draft['after'])
        self.assertIsNone(refreshed['replacement']['advice']['choice'])
        self.state.write_bytes(self.original + b'concurrent: retained\n')
        blocked = service.reply(draft, 'Apply')
        self.assertEqual(blocked['state'], 'blocked')
        self.assertIn('Inputs changed', blocked['message'])
        self.assertFalse((self.project / '.playbook-config.json').exists())

    def test_accept_preserves_repair_threshold_and_other_draft_values(self):
        service = self.service()
        draft = service.read()
        edited = service.reply(service.reply(draft, 'Edit Repair'), '1')
        thresholds = {key: value for key, value in edited['after']['escalated_repair'].items()
                      if key in {'trigger_unsuccessful_repairs', 'cycles_per_slice', 'scope', 'authority'}}
        refreshed = service.reply(edited, 'Refresh')
        accepted = service.reply(refreshed, 'Accept replacement')
        self.assertEqual(accepted['after']['escalated_repair'], edited['after']['escalated_repair'])
        self.assertEqual({key: accepted['after']['escalated_repair'][key] for key in thresholds}, thresholds)
        self.assertEqual(self.state.read_bytes(), self.original)


    def assert_unsaved(self, result):
        self.assertFalse(result['launched'])
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), ['.playbook-state.yml'])

    def assert_recovery(self, result, original):
        self.assertEqual(result['after'], original['after'])
        self.assertEqual(result['before'], original['before'])
        self.assertEqual(result['step'], 'replacement')
        self.assertIn('Refresh', result['choices'])
        self.assertIn('Choose another model', result['choices'])
        self.assert_unsaved(result)

    def test_accept_rechecks_original_guidance_at_inclusive_boundary(self):
        now = [fixtures.NOW]
        fetches = []
        def sources():
            fetches.append(1)
            return deepcopy(self.evidence)
        service = Configuration(self.project, self.discover, lambda: now[0],
                                context=self.context, recommendation_sources=sources)
        original = service.read()
        role = original['replacement']['role']
        for age in (86399, 86400, 86401):
            with self.subTest(age=age):
                now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00')) + timedelta(seconds=age)).isoformat()
                result = service.reply(original, 'Accept replacement')
                if age <= 86400:
                    self.assertEqual(result['step'], 'preview')
                    self.assertEqual(result['after'][role]['model_id'], 'fixture-code')
                else:
                    self.assert_recovery(result, original)
                    self.assertNotIn('Accept replacement', result['choices'])
                    self.assertIsNone(result['recommendations'][role]['choice'])
                self.assert_unsaved(result)
        self.assertEqual(fetches, [1])

    def test_guidance_expiring_between_exact_boundary_read_and_accept(self):
        now = ['2026-10-02T12:00:00Z']
        service = Configuration(self.project, self.discover, lambda: now[0],
                                context=self.context, recommendation_sources=lambda: deepcopy(self.evidence))
        original = service.read()
        self.assertIn('Accept replacement', original['choices'])
        now[0] = '2026-10-02T12:00:01Z'
        result = service.reply(original, 'Accept replacement')
        self.assert_recovery(result, original)
        self.assertNotIn('Accept replacement', result['choices'])

    def test_accept_rejects_future_missing_and_malformed_original_claim(self):
        service = self.service()
        original = service.read()
        for date in ('2027-10-01T12:00:00Z', None, 'not-a-date'):
            with self.subTest(date=date):
                # Simulate a sealed persisted proposal from an older reader.
                draft = deepcopy(original)
                draft['replacement']['advice']['guidance']['checked_at'] = date
                for claim in draft['recommendation_evidence']['guidance']:
                    claim['checked_at'] = date
                draft['proposal_revision'] = Configuration._revision(draft)
                result = service.reply(draft, 'Accept replacement')
                self.assert_recovery(result, draft)
                self.assertNotIn('Accept replacement', result['choices'])

    def test_accept_revalidates_specific_claim_task_risk_and_role_policy(self):
        service = self.service()
        original = service.read()
        for change in ('task', 'risk', 'permission', 'reasoning'):
            with self.subTest(change=change):
                draft = deepcopy(original)
                role = draft['replacement']['role']
                if change in ('task', 'risk'):
                    draft['context'][change] = 'unsupported'
                elif change == 'permission':
                    draft['context']['constraints'] = {role: {'permission': False}}
                else:
                    draft['replacement']['advice']['guidance']['reasoning'] = ['low']
                    draft['recommendation_evidence']['guidance'][0]['reasoning'] = ['low']
                draft['proposal_revision'] = Configuration._revision(draft)
                self.assert_recovery(service.reply(draft, 'Accept replacement'), draft)

    def test_accept_invalidates_changed_availability_or_version_without_fetching(self):
        original_routes = deepcopy(self.routes)
        for change in ('route', 'revision'):
            with self.subTest(change=change):
                self.routes = deepcopy(original_routes)
                revision = ['fixture']
                fetches = []
                def discover(request):
                    return {**self.discover(request), 'revision': revision[0]}
                def sources():
                    fetches.append(1)
                    return deepcopy(self.evidence)
                service = Configuration(self.project, discover, lambda: fixtures.NOW,
                                        context=self.context, recommendation_sources=sources)
                original = service.read()
                if change == 'route':
                    self.routes.pop(0)
                else:
                    revision[0] = 'new-source-version'
                result = service.reply(original, 'Accept replacement')
                self.assert_recovery(result, original)
                self.assertEqual(fetches, [1])
                self.assertIn('Refresh', result['message'])
                self.assertNotIn('Accept replacement', result['choices'])
                self.assert_recovery(service.reply(result, 'Accept replacement'), original)
                self.assertEqual(fetches, [1])

    def test_missing_or_expired_pricing_does_not_prevent_valid_acceptance(self):
        for rates in ([], [{**self.evidence['rates'][0], 'checked_at': '2020-01-01T00:00:00Z'}]):
            with self.subTest(rates=rates):
                self.evidence['rates'] = rates
                service = self.service()
                original = service.read()
                result = service.reply(original, 'Accept replacement')
                self.assertEqual(result['step'], 'preview')
                self.assertEqual(result['after'][original['replacement']['role']]['model_id'], 'fixture-code')
                self.assert_unsaved(result)

    def cli(self, action, request, now, source, cache):
        adapter = "import json,sys; r=json.load(sys.stdin); json.dump(dict(request_id=r['request_id'],checked_at=r['started_at'],authority='host-reported-selection',revision='fixture',routes=" + repr(self.routes) + "),sys.stdout)"
        process = subprocess.run([sys.executable, str(Path(__file__).with_name('configure-playbook.py')),
                                  '--project', str(self.project), '--now', now,
                                  '--evidence-fixture', str(source), '--evidence-dir', str(cache),
                                  '--discovery-command', json.dumps([sys.executable, '-c', adapter]), action],
                                 input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        result = json.loads(process.stdout)
        self.assert_unsaved(result)
        return result

    def test_cli_stale_sealed_proposal_and_persisted_cache_preserve_draft(self):
        with tempfile.TemporaryDirectory() as private:
            source, cache = Path(private) / 'source.json', Path(private) / 'cache'
            source.write_text(json.dumps(self.evidence))
            original = self.cli('read', {'context': self.context}, '2026-10-02T12:00:00Z', source, cache)
            self.assertIn('Accept replacement', original['choices'])
            cache_before = {p.name: p.read_bytes() for p in cache.iterdir()}
            source.unlink()  # Accept must neither fetch nor rely on the source envelope.
            for now, usable in (('2026-10-02T11:59:59Z', True), ('2026-10-02T12:00:00Z', True),
                                ('2026-10-02T12:00:01Z', False), ('2026-09-30T12:00:00Z', False)):
                with self.subTest(now=now):
                    result = self.cli('reply', {'proposal': original, 'reply': 'Accept replacement'}, now, source, cache)
                    if usable:
                        self.assertEqual(result['step'], 'preview')
                    else:
                        self.assert_recovery(result, original)
                        self.assertNotIn('Accept replacement', result['choices'])
            self.assertEqual({p.name: p.read_bytes() for p in cache.iterdir()}, cache_before)
            reloaded = self.cli('read', {'context': self.context}, '2026-10-02T12:00:01Z', source, cache)
            self.assertNotIn('Accept replacement', reloaded['choices'])
            result = self.cli('reply', {'proposal': reloaded, 'reply': 'Accept replacement'},
                              '2026-10-02T12:00:01Z', source, cache)
            self.assert_recovery(result, reloaded)

    def test_cli_missing_and_malformed_claim_in_retained_proposal(self):
        with tempfile.TemporaryDirectory() as private:
            source, cache = Path(private) / 'source.json', Path(private) / 'cache'
            source.write_text(json.dumps(self.evidence))
            original = self.cli('read', {'context': self.context}, fixtures.NOW, source, cache)
            source.unlink()
            for date in (None, 'invalid'):
                draft = deepcopy(original)
                draft['replacement']['advice']['guidance']['checked_at'] = date
                for claim in draft['recommendation_evidence']['guidance']:
                    claim['checked_at'] = date
                draft['proposal_revision'] = Configuration._revision(draft)
                result = self.cli('reply', {'proposal': draft, 'reply': 'Accept replacement'}, fixtures.NOW, source, cache)
                self.assert_recovery(result, draft)
                self.assertNotIn('Accept replacement', result['choices'])


if __name__ == '__main__':
    unittest.main()
