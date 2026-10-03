"""Original selected guidance and numeric caller recovery at public seams."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import unittest
from unittest.mock import patch

import test_model_subtotal_projection as subtotal


class InputBoundaryTests(unittest.TestCase):
    setUp = subtotal.SubtotalProjectionTests.setUp
    discover = subtotal.SubtotalProjectionTests.discover
    conversation = subtotal.SubtotalProjectionTests.conversation
    prepare = subtotal.SubtotalProjectionTests.prepare
    copies = staticmethod(subtotal.SubtotalProjectionTests.copies)
    seal = staticmethod(subtotal.SubtotalProjectionTests.seal)
    exercise = subtotal.SubtotalProjectionTests.exercise
    actions = subtotal.SubtotalProjectionTests.actions

    def test_nonfinite_caller_recovery_all_actions_and_nested_retention(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.prepare(surface)
            for number in (float('nan'), float('inf'), -float('inf')):
                for location in ('root', 'display', 'nested'):
                    draft = deepcopy(original)
                    if location == 'root':
                        draft['recommendations']['implementation']['cost']['estimate']['amount'] = number
                    elif location == 'display':
                        draft['replacement']['advice']['cost']['estimate']['amount'] = number
                    else:
                        draft['retained_proposal'] = deepcopy(original)
                        draft['retained_proposal']['recommendations']['implementation']['cost']['estimate']['amount'] = number
                    # Do not reseal: a malformed caller must never gain authority.
                    for action in self.actions:
                        with self.subTest(surface=surface, number=str(number), location=location, action=action):
                            request = ({'state': 'blocked', 'retained_proposal': draft}
                                       if action == 'caller recovery Back' else draft)
                            result = invoke(request, 'Back' if action == 'caller recovery Back' else action)
                            self.assertIn(result['state'], ('blocked', 'recovery_required'))
                            self.assertFalse(result['launched'])
                            self.assertNotIn('retained_proposal', result)
                            self.assertTrue(result['message'])
                            json.dumps(result, allow_nan=False)
                            unchanged()
            # The wire input remains legal JSON; overflow is distinct from NaN tokens.
            if surface == 'cli':
                draft = deepcopy(original)
                draft['recommendations']['implementation']['cost']['estimate']['amount'] = float('inf')
                dumps = json.dumps
                for literal in ('1e309', '-1e309'):
                    with patch('test_model_advice_projection.json.dumps',
                               side_effect=lambda *a, **kw: dumps(*a, **kw).replace('Infinity', literal)):
                        for action in self.actions:
                            result = invoke(draft, action if action != 'caller recovery Back' else 'Back')
                            self.assertEqual(result['state'], 'blocked')
                            self.assertNotIn('retained_proposal', result)
                            unchanged()

    def test_guidance_fit_original_root_all_actions_boundaries_and_repeats(self):
        mutations = ({'model_id': 'unselected-sibling'}, {'provider': 'anthropic'},
                     {'tasks': ['analysis']}, {'risks': ['high']}, {'reasoning': ['low']},
                     {'tasks': 'coding'}, {'risks': None}, {'text': ''})
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.prepare(surface)
            checked = datetime.fromisoformat(original['recommendations']['implementation']['guidance']['checked_at'].replace('Z', '+00:00'))
            for mutation in mutations:
                for ownership in ('all', 'root'):
                    draft = deepcopy(original)
                    targets = self.copies(draft) if ownership == 'all' else draft['recommendations'].values()
                    for advice in targets:
                        advice['guidance'].update(mutation)
                    self.seal(draft)
                    for age in (86399, 86400, 86401):
                        now[0] = (checked + timedelta(seconds=age)).isoformat()
                        for action in self.actions:
                            with self.subTest(surface=surface, mutation=mutation, ownership=ownership, age=age, action=action):
                                retained = self.exercise(invoke, draft, action)
                                for repeat in (None, 'Explain Build', 'Back', 'Presets', ['invalid reply']):
                                    if repeat is not None:
                                        retained = self.exercise(invoke, retained, repeat)
                                    self.assertEqual(retained['after'], original['after'])
                                    self.assertNotIn('Accept replacement', retained.get('choices', []))
                                    for advice in self.copies(retained):
                                        self.assertIsNone(advice['choice'])
                                        self.assertIsNone(advice['cost'])
                                        claim = advice['withheld_evidence']['guidance']
                                        root = draft['recommendations']['implementation']['guidance']
                                        for key in ('model_id', 'provider', 'tasks', 'risks', 'reasoning', 'text', 'checked_at'):
                                            self.assertEqual(claim.get(key), root.get(key))
                                        self.assertEqual(advice['withheld_evidence']['rates']['input'], 2)
                                        self.assertIn('Refresh', advice['limitations'])
                                    unchanged()

    def test_valid_guidance_finite_cost_and_draft_only_accept(self):
        for surface in ('library', 'cli'):
            invoke, now, draft, unchanged = self.prepare(surface)
            checked = datetime.fromisoformat(draft['recommendations']['implementation']['guidance']['checked_at'].replace('Z', '+00:00'))
            for age in (86399, 86400, 86401):
                now[0] = (checked + timedelta(seconds=age)).isoformat()
                for action in self.actions:
                    retained = self.exercise(invoke, draft, action)
                    advice = retained['recommendations']['implementation']
                    if age <= 86400:
                        self.assertEqual(advice['choice']['model_id'], 'fixture-code')
                        self.assertEqual(advice['cost']['estimate']['amount'], 8)
                        expected = deepcopy(draft['after'])
                        if action == 'Accept replacement':
                            role = draft['replacement']['role']
                            expected[role] = deepcopy(draft['recommendations'][role]['choice'])
                        self.assertEqual(retained['after'], expected)
                    else:
                        self.assertIsNone(advice['choice'])
                        self.assertIsNone(advice['cost'])
                    unchanged()


if __name__ == '__main__':
    unittest.main()
