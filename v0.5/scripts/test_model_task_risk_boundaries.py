"""Suitability requires scalar task/risk evidence, not matching JSON shapes.

Exercise the public read, lane and retained proposal contracts with synthetic
claims. Reuse public conversation fixtures, never provider execution.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_model_recommendations as fixtures
import test_model_subtotal_projection as projection


class TaskRiskBoundaryTests(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover
    service = fixtures.RecommendationTests.service
    conversation = projection.SubtotalProjectionTests.conversation
    prepare = projection.SubtotalProjectionTests.prepare
    copies = staticmethod(projection.SubtotalProjectionTests.copies)
    seal = staticmethod(projection.SubtotalProjectionTests.seal)
    exercise = projection.SubtotalProjectionTests.exercise
    actions = projection.SubtotalProjectionTests.actions
    malformed = (['coding'], {'value': 'coding'}, True, 1, 1.5)

    def cases(self):
        for field, plural in (('task', 'tasks'), ('risk', 'risks')):
            for value in self.malformed:
                # Both aligned malformed equality and a malformed extra element
                # beside legitimate fit must withhold the entire selected claim.
                for aligned in (True, False):
                    yield field, plural, value, aligned

    def test_fresh_read_and_lane_withhold_malformed_fit_library_and_cli(self):
        for surface in ('library', 'cli'):
            for field, plural, value, aligned in self.cases():
                with self.subTest(surface=surface, field=field, value=value, aligned=aligned):
                    context = deepcopy(self.context)
                    context['workload'] = dict(input_tokens=1000, output_tokens=500, retries=2,
                                               billing_route='standard-short-context-uncached')
                    context['constraints'] = {'implementation': {'authority': True, 'permission': True}}
                    if aligned:
                        context[field] = deepcopy(value)
                    evidence = deepcopy(self.evidence)
                    evidence['guidance'] = [evidence['guidance'][0]]
                    selected = evidence['guidance'][0]
                    selected[plural] = [deepcopy(value)] if aligned else [context[field], deepcopy(value)]
                    feature = {'model_id': 'active-feature', 'runner': 'codex', 'reasoning': 'high'}
                    if surface == 'library':
                        service = self.service(context, sources=lambda: deepcopy(evidence))
                        read = service.read()
                        lane = service.advise('implementation', feature)
                    else:
                        with tempfile.TemporaryDirectory() as temporary:
                            source = Path(temporary) / 'evidence.json'
                            source.write_text(json.dumps(evidence))
                            adapter = "import json,sys; r=json.load(sys.stdin); json.dump(dict(request_id=r['request_id'],checked_at=r['started_at'],authority='host-reported-selection',revision='fixture',routes=" + repr(self.routes) + "),sys.stdout)"
                            def run(action, request):
                                process = subprocess.run([sys.executable, str(Path(__file__).with_name('configure-playbook.py')),
                                    '--project', str(self.project), '--now', fixtures.NOW,
                                    '--evidence-dir', str(Path(temporary) / 'cache'), '--evidence-fixture', str(source),
                                    '--discovery-command', json.dumps([sys.executable, '-c', adapter]), action],
                                    input=json.dumps(request), text=True, capture_output=True)
                                self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
                                self.assertEqual(process.stderr, '')
                                return json.loads(process.stdout)
                            read = run('read', {'context': context})
                            lane = run('advise', {'role': 'implementation', 'context': context, 'feature_choice': feature})
                    for advice in (read['recommendations']['implementation'], lane['recommendation']):
                        self.assertIsNone(advice['choice'])
                        self.assertIsNone(advice['cost'])
                    self.assertEqual(read['recommendation_evidence']['guidance'][0]['text'], selected['text'])
                    self.assertEqual(read['recommendation_evidence']['guidance'][0]['checked_at'], fixtures.NOW)
                    self.assertEqual(lane['effective']['choice'], feature)
                    self.assertFalse(read['launched'])
                    self.assertFalse(lane['launched'])
                    self.assertEqual(self.state.read_bytes(), self.original)
                    self.assertFalse((self.project / '.playbook-config.json').exists())

    def assert_withheld(self, retained, draft):
        self.assertEqual(retained['after'], draft['after'])
        self.assertEqual(retained['before'], draft['before'])
        self.assertEqual(retained['personal'], draft['personal'])
        self.assertNotIn('Accept replacement', retained.get('choices', []))
        for advice in self.copies(retained):
            self.assertIsNone(advice['choice'])
            self.assertIsNone(advice['guidance'])
            self.assertIsNone(advice['cost'])
            root = draft['recommendations']['implementation']
            for kind, original in (('guidance', root['guidance']), ('rates', root['cost']['rates'])):
                claim = advice['withheld_evidence'][kind]
                for key, expected in original.items():
                    if key != 'status':
                        self.assertEqual(claim[key], expected)
            self.assertIn('Refresh', advice['limitations'])

    def test_sealed_and_persisted_fit_all_actions_copies_boundaries_and_repeats(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.prepare(surface)
            checked = datetime.fromisoformat(original['recommendations']['implementation']['guidance']['checked_at'].replace('Z', '+00:00'))
            for field, plural, value, aligned in self.cases():
                for ownership in ('all', 'root'):
                    draft = deepcopy(original)
                    if aligned:
                        draft['context'][field] = deepcopy(value)
                    targets = self.copies(draft) if ownership == 'all' else draft['recommendations'].values()
                    for advice in targets:
                        advice['guidance'][plural] = ([deepcopy(value)] if aligned else
                                                     [draft['context'][field], deepcopy(value)])
                    self.seal(draft)
                    # Persist/reload the sealed wire data independently of the
                    # in-memory draft. Valid nested/sibling text cannot replace it.
                    with tempfile.TemporaryDirectory() as temporary:
                        saved = Path(temporary) / 'proposal.json'
                        saved.write_text(json.dumps(draft))
                        draft = json.loads(saved.read_text())
                    untouched = deepcopy(draft)
                    for age in (86399, 86400, 86401):
                        now[0] = (checked + timedelta(seconds=age)).isoformat()
                        with self.subTest(surface=surface, field=field, value=value, aligned=aligned,
                                          ownership=ownership, age=age):
                            with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Unexpected GET')):
                                for action in self.actions:
                                    retained = self.exercise(invoke, draft, action)
                                    self.assert_withheld(retained, draft)
                                    unchanged()
                                for repeat in ('Explain Build', 'Back', 'Presets', ['invalid reply'], 'Accept replacement'):
                                    retained = self.exercise(invoke, retained, repeat)
                                    self.assert_withheld(retained, draft)
                                    unchanged()
                            self.assertEqual(draft, untouched)

    def test_valid_scalar_and_goal_inference_controls(self):
        for field in (None, 'task', 'risk', 'both'):
            context = deepcopy(self.context)
            if field in ('task', 'both'):
                context.pop('task')
            if field in ('risk', 'both'):
                context.pop('risk')
            context['workload'] = dict(input_tokens=1000, output_tokens=500, retries=2,
                                       billing_route='standard-short-context-uncached')
            advice = self.service(context).read()['recommendations']['implementation']
            self.assertEqual(advice['choice']['model_id'], 'fixture-code')
            self.assertEqual(advice['cost']['estimate']['amount'], .015)
        # Exact retained boundary and draft-only Accept controls are already
        # public; run that same independent expected-$8 control here as well.
        import test_model_input_boundaries as boundaries
        boundaries.InputBoundaryTests.test_valid_guidance_finite_cost_and_draft_only_accept(self)

    def test_inadequate_fit_keeps_editor_and_explicit_refresh_recovery(self):
        for surface in ('library', 'cli'):
            for field, plural in (('task', 'tasks'), ('risk', 'risks')):
                invoke, now, original, unchanged = self.conversation(surface, None, keep_source=True)
                for value in (None, '', ' ', ['coding']):
                    draft = deepcopy(original)
                    draft['context'][field] = value
                    for advice in self.copies(draft):
                        advice['guidance'][plural] = [value]
                    self.seal(draft)
                    retained = self.exercise(invoke, draft, 'Accept replacement')
                    self.assert_withheld(retained, draft)
                    editor = invoke(retained, 'Edit ' + original['replacement']['role'])
                    self.assertEqual(editor['step'], 'edit')
                    self.assertEqual(editor['edit_role'], original['replacement']['role'])
                    self.assertEqual(editor['after'], original['after'])
                    unchanged()
                # With valid requested values, only an explicit new retrieval
                # may replace malformed selected evidence with fresh evidence.
                draft = deepcopy(original)
                for advice in self.copies(draft):
                    advice['guidance'][plural].append({'invalid': True})
                self.seal(draft)
                retained = self.exercise(invoke, draft, 'Back')
                self.assert_withheld(retained, draft)
                unchanged()
                refreshed = invoke(retained, 'Refresh')
                self.assertEqual(refreshed['recommendations']['implementation']['choice']['model_id'], 'fixture-code')
                self.assertEqual(refreshed['recommendations']['implementation']['cost']['estimate']['amount'], 20)
                self.assertEqual(refreshed['after'], original['after'])
                self.assertFalse(refreshed['launched'])
                self.assertEqual(self.state.read_bytes(), self.original)
                self.assertFalse((self.project / '.playbook-config.json').exists())


if __name__ == '__main__':
    unittest.main()
