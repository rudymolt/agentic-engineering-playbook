"""Public cost contract: selected rates must support the supplied subtotal.

Synthetic prices/workloads only; no provider qualification or model execution.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import unittest

import test_model_estimate_projection as projection
import test_model_recommendations as fixtures


class SubtotalProjectionTests(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover
    conversation = projection.EstimateProjectionTests.conversation
    copies = staticmethod(projection.EstimateProjectionTests.copies)
    seal = staticmethod(projection.EstimateProjectionTests.seal)
    actions = ('Explain Build', 'Back', 'Presets', ['invalid reply'],
               'caller recovery Back', 'Accept replacement')

    def prepare(self, surface, cli_sample=True):
        invoke, now, original, unchanged = self.conversation(surface, None, cli_sample=cli_sample)
        # Independent hand calculation: (1M * $2 + .5M * $4) * 2 = $8.
        original['context']['workload']['output_tokens'] = 500000
        for advice in self.copies(original):
            advice['cost']['rates']['output'] = 4
            advice['cost']['estimate']['assumptions']['output_tokens'] = 500000
            advice['cost']['estimate']['amount'] = 8
        self.seal(original)
        return invoke, now, original, unchanged

    def exercise(self, invoke, draft, action):
        request = ({'state': 'blocked', 'retained_proposal': deepcopy(draft)}
                   if action == 'caller recovery Back' else draft)
        result = invoke(request, 'Back' if action == 'caller recovery Back' else action)
        self.assertFalse(result.get('launched', False))
        return result.get('retained_proposal', result)

    def assert_projection(self, retained, draft, usable, expected=None, accept=False):
        role = draft['replacement']['role']
        expected_after = deepcopy(draft['after'])
        if accept and usable:
            expected_after[role] = deepcopy(draft['recommendations'][role]['choice'])
        self.assertEqual(retained['after'], expected_after)
        self.assertEqual(retained['before'], draft['before'])
        self.assertEqual(retained['personal'], draft['personal'])
        for advice in self.copies(retained):
            if not usable:
                self.assertIsNone(advice['choice'])
                self.assertIsNone(advice['cost'])
                self.assertEqual(advice['withheld_evidence']['guidance']['checked_at'],
                                 draft['recommendations'][role]['guidance']['checked_at'])
            else:
                self.assertEqual(advice['guidance'], draft['recommendations'][role]['guidance'])
                self.assertEqual(advice['cost']['rates'], draft['recommendations'][role]['cost']['rates'])
                self.assertEqual(advice['cost']['estimate'], expected)
                if expected is None and draft['recommendations'][role]['cost']['estimate'] is not None:
                    original_estimate = draft['recommendations'][role]['cost']['estimate']
                    withheld = advice['withheld_evidence']['estimate']
                    for key, value in original_estimate.items():
                        if key != 'status':
                            self.assertEqual(withheld[key], value)
                    self.assertIn('Refresh', advice['limitations'])
        self.assertTrue(list(self.copies(retained)))

    def test_f1_shapes_all_actions_fresh_and_exact_claim_boundaries(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.prepare(surface)
            checked = datetime.fromisoformat(original['recommendations']['implementation']['guidance']['checked_at'].replace('Z', '+00:00'))
            for shape in ('billing_route', 'changed_rate', 'boolean_amount'):
                draft = deepcopy(original)
                for advice in self.copies(draft):
                    if shape == 'billing_route':
                        advice['cost']['rates']['billing_route'] = 'batch'
                    elif shape == 'changed_rate':
                        advice['cost']['rates']['input'] = 7  # Would imply $18, never substitute it.
                    else:
                        advice['cost']['estimate']['amount'] = True
                self.seal(draft)
                untouched = deepcopy(draft)
                for age in (0, 1, 2, 86399, 86400, 86401):
                    now[0] = (checked + timedelta(seconds=age)).isoformat()
                    for action in self.actions:
                        with self.subTest(surface=surface, shape=shape, age=age, action=action):
                            retained = self.exercise(invoke, draft, action)
                            self.assert_projection(retained, draft, age <= 86400,
                                                   accept=action == 'Accept replacement')
                            for repeat in ('Explain Build', 'Back', 'Presets'):
                                retained = self.exercise(invoke, retained, repeat)
                                self.assert_projection(retained, draft, age <= 86400,
                                                       accept=action == 'Accept replacement')
                            unchanged()
                            self.assertEqual(draft, untouched)

    def test_valid_subtotal_is_unchanged_and_accept_is_draft_only(self):
        for surface in ('library', 'cli'):
            invoke, now, draft, unchanged = self.prepare(surface)
            checked = datetime.fromisoformat(draft['recommendations']['implementation']['guidance']['checked_at'].replace('Z', '+00:00'))
            estimate = deepcopy(draft['recommendations']['implementation']['cost']['estimate'])
            for age in (0, 86399, 86400, 86401):
                now[0] = (checked + timedelta(seconds=age)).isoformat()
                for action in self.actions:
                    with self.subTest(surface=surface, age=age, action=action):
                        retained = self.exercise(invoke, draft, action)
                        self.assert_projection(retained, draft, age <= 86400,
                                               expected=estimate if age <= 86400 else None,
                                               accept=action == 'Accept replacement')
                        unchanged()

    def test_self_consistent_subtotal_requires_the_requested_workload(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.prepare(surface)
            for workload in (None, {}, [], {**original['context']['workload'], 'input_tokens': 3000000},
                             {**original['context']['workload'], 'retries': True}):
                draft = deepcopy(original)
                draft['context']['workload'] = workload
                self.seal(draft)
                for action in self.actions:
                    with self.subTest(surface=surface, workload=workload, action=action):
                        # The estimate remains internally consistent at $8; context
                        # instead requests $16 in the changed-input case. Do not
                        # treat its self-described assumptions as context authority.
                        retained = self.exercise(invoke, draft, action)
                        accepted = action == 'Accept replacement' and isinstance(workload, dict)
                        self.assert_projection(retained, draft, True, accept=accepted)
                        self.assert_projection(self.exercise(invoke, retained, 'Back'), draft, True,
                                               accept=accepted)
                        unchanged()

    def test_malformed_assumptions_metadata_and_amounts_preserve_suitability(self):
        mutations = [
            ('assumptions', None), ('assumptions', []), ('assumptions', {}),
            ('source_url', None), ('source_url', fixtures.GUIDANCE),
            ('checked_at', None), ('checked_at', '2026-10-02T11:59:58Z'),
            ('uncertainty', None), ('label', None), ('currency', 'EUR'),
            *[('amount', value) for value in (None, False, '8', [], {}, -1, 2**53, 10**400, 8.00000001)],
        ]
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.prepare(surface)
            for key, value in mutations:
                for missing in (False, True):
                    with self.subTest(surface=surface, key=key, value=value, missing=missing):
                        draft = deepcopy(original)
                        for advice in self.copies(draft):
                            if missing:
                                advice['cost']['estimate'].pop(key, None)
                            else:
                                advice['cost']['estimate'][key] = value
                        self.seal(draft)
                        retained = self.exercise(invoke, draft, 'Accept replacement')
                        self.assert_projection(retained, draft, True, accept=True)
                        retained = self.exercise(invoke, retained, 'Explain Build')
                        self.assert_projection(retained, draft, True, accept=True)
                        unchanged()

    def test_invalid_estimate_status_and_explicit_editor_refresh_recovery(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.prepare(surface)
            for status in ('failed', 'stale', [], {}, True, 1):
                draft = deepcopy(original)
                for advice in self.copies(draft):
                    advice['cost']['estimate']['status'] = status
                self.seal(draft)
                retained = self.exercise(invoke, draft, 'Back')
                self.assert_projection(retained, draft, True)
                editor = invoke(retained, 'Edit ' + original['replacement']['role'])
                self.assertEqual(editor['step'], 'edit')
                self.assertEqual(editor['edit_role'], original['replacement']['role'])
                unchanged()
            # Refresh is the explicit authority to obtain a new subtotal.
            invoke, now, original, unchanged = self.conversation(surface, None, keep_source=True)
            draft = deepcopy(original)
            for advice in self.copies(draft):
                advice['cost']['estimate']['amount'] = True
            self.seal(draft)
            retained = self.exercise(invoke, draft, 'Back')
            self.assert_projection(retained, draft, True)
            unchanged()
            refreshed = invoke(retained, 'Refresh')
            self.assertEqual(refreshed['recommendations']['implementation']['cost']['estimate']['amount'], 20)
            self.assertEqual(refreshed['after'], original['after'])
            self.assertEqual(self.state.read_bytes(), self.original)
            self.assertFalse((self.project / '.playbook-config.json').exists())

    def test_bounded_counts_and_independently_dated_selected_claims(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.prepare(surface)
            for key in ('input_tokens', 'output_tokens', 'retries', 'billing_route'):
                for value in (None, True, -1, 2**53, 10**400, '1'):
                    with self.subTest(surface=surface, key=key, value=value):
                        draft = deepcopy(original)
                        for advice in self.copies(draft):
                            advice['cost']['estimate']['assumptions'][key] = value
                        self.seal(draft)
                        self.assert_projection(self.exercise(invoke, draft, 'Back'), draft, True)
                        unchanged()
            # Large but bounded counts can still support a finite unchanged subtotal.
            draft = deepcopy(original)
            for advice in self.copies(draft):
                rate, estimate = advice['cost']['rates'], advice['cost']['estimate']
                rate.update(input=0, output=0)
                estimate['assumptions'].update(input_tokens=2**53-1, output_tokens=2**53-1, retries=2**53-1)
                estimate['amount'] = 0
            draft['context']['workload'].update(input_tokens=2**53-1, output_tokens=2**53-1, retries=2**53-1)
            self.seal(draft)
            self.assert_projection(self.exercise(invoke, draft, 'Back'), draft, True,
                                   expected=draft['recommendations']['implementation']['cost']['estimate'])
            # Pricing owns its date; a younger guidance claim cannot renew it.
            invoke, now, original, unchanged = self.conversation(surface, 'rates')
            for age in (86399, 86400, 86401):
                now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00')) + timedelta(seconds=age)).isoformat()
                retained = self.exercise(invoke, original, 'Back')
                selected = retained['recommendations']['implementation']
                self.assertIsNotNone(selected['guidance'])
                if age <= 86400:
                    self.assertEqual(selected['cost'], original['recommendations']['implementation']['cost'])
                else:
                    self.assertIsNone(selected['cost']['rates'])
                    self.assertIsNone(selected['cost']['estimate'])
                    self.assertEqual(selected['withheld_evidence']['rates']['checked_at'], fixtures.NOW)
                unchanged()


if __name__ == '__main__':
    unittest.main()
