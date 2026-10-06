"""Individual evidence status at public lane and replacement boundaries."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_model_recommendations as fixtures
import test_model_advice_projection as conversations
from playbook_config import Configuration


class ClaimStatusTests(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover
    conversation = conversations.AdviceProjectionTests.conversation
    assert_rejected_claim_owner = conversations.AdviceProjectionTests.assert_rejected_claim_owner

    def lane(self, surface, evidence):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        cache = root / 'cache'
        source = root / 'source.json'
        source.write_text(json.dumps(evidence))
        calls = []
        context = {**self.context, 'constraints': {'implementation': {'authority': True, 'permission': True}},
                   'workload': dict(input_tokens=1000000, output_tokens=500000, retries=2,
                                    billing_route='standard-short-context-uncached')}
        feature = dict(model_id='retained-feature', runner='codex', reasoning='high')
        adapter = ("import json,sys; r=json.load(sys.stdin); json.dump(dict(request_id=r['request_id'],"
                   "checked_at=r['started_at'],revision='fixture',authority='host-reported-selection',routes="
                   + repr(self.routes) + "),sys.stdout)")
        wrapper = root / 'cli.py'
        wrapper.write_text("import runpy,sys,urllib.request\nfrom pathlib import Path\n"
                           "def forbidden(*a,**k): raise AssertionError('Unexpected GET')\n"
                           "urllib.request.OpenerDirector.open=forbidden\n"
                           "sys.path.insert(0,str(Path(sys.argv[1]).parent))\n"
                           "runpy.run_path(sys.argv.pop(1),run_name='__main__')\n")

        def fetch():
            calls.append(1)
            return json.loads(source.read_text())

        def invoke(task='coding'):
            request_context = {**context, 'task': task}
            if surface == 'library':
                # New service each time proves persisted reuse, not an in-memory hit.
                service = Configuration(self.project, self.discover, lambda: fixtures.NOW,
                                        context=request_context, evidence_dir=cache, recommendation_sources=fetch)
                with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Unexpected GET')):
                    result = service.advise('implementation', feature)
            else:
                process = subprocess.run(
                    [sys.executable, str(wrapper), str(Path(__file__).with_name('configure-playbook.py')),
                     '--project', str(self.project), '--now', fixtures.NOW, '--evidence-dir', str(cache),
                     '--evidence-fixture', str(source), '--discovery-command',
                     json.dumps([sys.executable, '-c', adapter]), 'advise'],
                    input=json.dumps(dict(role='implementation', feature_choice=feature, context=request_context)),
                    text=True, capture_output=True)
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                self.assertEqual(process.stderr, '')
                result = json.loads(process.stdout)
            self.assertEqual(result['effective'], {'origin': 'feature', 'choice': feature})
            self.assertFalse(result['launched'])
            self.assertEqual(self.state.read_bytes(), self.original)
            self.assertFalse((self.project / '.playbook-config.json').exists())
            return result
        return invoke, source, cache, calls

    def evidence_with_sibling(self, metadata):
        evidence = deepcopy(self.evidence)
        evidence['rates'].append({**evidence['rates'][0], 'model_id': 'fixture-analysis'})
        if metadata:
            evidence['sources'] = [dict(source_url=url, checked_at=fixtures.NOW, status='retrieved')
                                   for url in (fixtures.GUIDANCE, fixtures.PRICING)]
        return evidence

    def assert_lane_withheld(self, result, kind, original):
        advice = result['recommendation']
        if kind == 'guidance':
            self.assertIsNone(advice['choice'])
            self.assertIsNone(advice['guidance'])
            self.assertIsNone(advice['cost'])
        else:
            self.assertEqual(advice['choice']['model_id'], 'fixture-code')
            self.assertIsNone(advice['cost']['rates'])
            self.assertIsNone(advice['cost']['estimate'])
        retained = next(record for record in result['recommendation_evidence'][kind]
                        if record['model_id'] == 'fixture-code')
        self.assertEqual({k: v for k, v in retained.items() if k != 'status'},
                         {k: v for k, v in original.items() if k != 'status'})
        self.assertIn(retained['status'], ('stale', 'incomplete', 'failed'))
        self.assertIn('Refresh', advice['limitations'])

    def test_lane_rejects_individual_status_on_fetch_and_persisted_reuse(self):
        for surface in ('library', 'cli'):
            for metadata in (False, True):
                for kind in ('guidance', 'rates'):
                    for status in ('unrecognized', [], {}, False, 7, 'stale', 'incomplete', 'failed'):
                        with self.subTest(surface=surface, metadata=metadata, kind=kind, status=status):
                            evidence = self.evidence_with_sibling(metadata)
                            evidence[kind][0]['status'] = status
                            invoke, source, cache, calls = self.lane(surface, evidence)
                            first = invoke()
                            self.assert_lane_withheld(first, kind, evidence[kind][0])
                            # A malformed sibling cannot erase successful analysis evidence.
                            sibling = invoke('analysis')['recommendation']
                            self.assertEqual(sibling['choice']['model_id'], 'fixture-analysis')
                            self.assertEqual(sibling['cost']['estimate']['amount'], 15)
                            source.unlink()
                            reused = invoke()
                            self.assert_lane_withheld(reused, kind, evidence[kind][0])

    def test_successful_statuses_reuse_at_exact_boundary_without_fetch_or_writes(self):
        for surface in ('library', 'cli'):
            for status in (None, 'retrieved'):
                with self.subTest(surface=surface, status=status):
                    evidence = self.evidence_with_sibling(True)
                    for kind in ('guidance', 'rates'):
                        for record in evidence[kind]:
                            record.update(status=status, checked_at='2026-09-30T12:00:00Z')
                    invoke, source, cache, calls = self.lane(surface, evidence)
                    initial = invoke()
                    before = {p.name: p.read_bytes() for p in cache.iterdir()}
                    source.unlink()
                    reused = invoke()
                    for result in (initial, reused):
                        advice = result['recommendation']
                        self.assertEqual(advice['choice']['model_id'], 'fixture-code')
                        self.assertEqual(advice['cost']['estimate']['amount'], 15)
                        self.assertEqual(advice['guidance']['checked_at'], '2026-09-30T12:00:00Z')
                    self.assertEqual({p.name: p.read_bytes() for p in cache.iterdir()}, before)
                    if surface == 'library':
                        self.assertEqual(calls, [1])

    def test_lane_invalid_dates_and_missing_price_preserve_valid_guidance(self):
        for surface in ('library', 'cli'):
            for kind in ('guidance', 'rates'):
                for date in (None, 'invalid-date', '2026-09-30T11:59:59Z', '2027-01-01T00:00:00Z'):
                    with self.subTest(surface=surface, kind=kind, date=date):
                        evidence = self.evidence_with_sibling(False)
                        evidence[kind][0].update(status='retrieved', checked_at=date)
                        invoke, source, cache, calls = self.lane(surface, evidence)
                        self.assert_lane_withheld(invoke(), kind, evidence[kind][0])
            evidence = self.evidence_with_sibling(False)
            evidence['rates'] = []
            invoke, source, cache, calls = self.lane(surface, evidence)
            advice = invoke()['recommendation']
            self.assertEqual(advice['choice']['model_id'], 'fixture-code')
            self.assertIsNone(advice['cost']['rates'])
            self.assertIsNone(advice['cost']['estimate'])

    def test_sealed_accept_checks_original_status_before_draft_edit(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'guidance')
            role = original['replacement']['role']
            for status in ('unrecognized', [], {}, False, 7, 'stale', 'incomplete', 'failed', None, 'retrieved'):
                with self.subTest(surface=surface, status=status):
                    draft = deepcopy(original)
                    draft['recommendations'][role]['guidance']['status'] = status
                    draft['replacement']['advice'] = deepcopy(draft['recommendations'][role])
                    draft['proposal_revision'] = Configuration._revision(draft)
                    before = deepcopy(draft)
                    result = invoke(draft, 'Accept replacement')
                    if status is None or status == 'retrieved':
                        self.assertEqual(result['after'][role]['model_id'], 'fixture-code')
                        self.assertEqual(result['step'], 'preview')
                    else:
                        retained = self.assert_rejected_claim_owner(result, original, draft['recommendations'][role])
                        self.assertIn('Refresh', retained['choices'])
                        editor = invoke(retained, 'Choose another model')
                        self.assertEqual(editor['step'], 'edit')
                        self.assertEqual(editor['edit_role'], role)
                        for action in ('Accept replacement', 'Explain ' + role, 'Back'):
                            retained = self.assert_rejected_claim_owner(invoke(retained, action), original,
                                                                       draft['recommendations'][role])
                        editor = invoke(retained, 'Edit ' + role)
                        self.assertEqual(editor['step'], 'edit')
                        self.assertEqual(editor['edit_role'], role)
                        self.assertEqual(invoke(retained, 'Not now')['state'], 'unchanged')
                    self.assertEqual(draft, before)
                    unchanged()

    def test_sealed_accept_with_bad_price_keeps_suitability_but_withholds_subtotal(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'rates')
            role = original['replacement']['role']
            for status in ('unrecognized', [], {}, 'failed'):
                with self.subTest(surface=surface, status=status):
                    draft = deepcopy(original)
                    rate = draft['recommendations'][role]['cost']['rates']
                    rate['status'] = status
                    draft['replacement']['advice'] = deepcopy(draft['recommendations'][role])
                    draft['proposal_revision'] = Configuration._revision(draft)
                    before = deepcopy(draft)
                    result = invoke(draft, 'Accept replacement')
                    self.assertEqual(result['after'][role]['model_id'], 'fixture-code')
                    advice = result['recommendations'][role]
                    self.assertEqual(advice['guidance'], draft['recommendations'][role]['guidance'])
                    self.assertIsNone(advice['cost']['rates'])
                    self.assertIsNone(advice['cost']['estimate'])
                    retained = advice['withheld_evidence']['rates']
                    self.assertEqual({k: v for k, v in retained.items() if k != 'status'},
                                     {k: v for k, v in rate.items() if k != 'status'})
                    self.assertEqual(draft, before)
                    unchanged()

    def test_invalid_status_accept_recovers_via_explicit_refresh(self):
        for surface in ('library', 'cli'):
            with self.subTest(surface=surface):
                invoke, now, original, unchanged = self.conversation(surface, 'guidance', keep_source=True)
                role = original['replacement']['role']
                draft = deepcopy(original)
                draft['recommendations'][role]['guidance']['status'] = 'unrecognized'
                draft['replacement']['advice'] = deepcopy(draft['recommendations'][role])
                draft['proposal_revision'] = Configuration._revision(draft)
                rejected = invoke(draft, 'Accept replacement')
                self.assertEqual(rejected['after'], original['after'])
                unchanged()
                refreshed = invoke(rejected, 'Refresh')
                self.assertEqual(refreshed['after'], original['after'])
                self.assertIn('Accept replacement', refreshed['choices'])
                accepted = invoke(refreshed, 'Accept replacement')
                self.assertEqual(accepted['after'][role]['model_id'], 'fixture-code')
                self.assertEqual(self.state.read_bytes(), self.original)
                self.assertFalse((self.project / '.playbook-config.json').exists())


if __name__ == '__main__':
    unittest.main()
