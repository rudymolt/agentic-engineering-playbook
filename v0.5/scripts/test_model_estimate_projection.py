"""Public cost claims need their original rate, even in resealed caller drafts."""

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import unittest

import test_model_advice_projection as projection
import test_model_recommendations as fixtures


class EstimateProjectionTests(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover
    conversation = projection.AdviceProjectionTests.conversation

    @staticmethod
    def seal(draft):
        # Public wire checksum: integrity of caller data is not evidence authority.
        content = {key: value for key, value in draft.items() if key != 'proposal_revision'}
        draft['proposal_revision'] = hashlib.sha256(
            (json.dumps(content, sort_keys=True, indent=2) + '\n').encode()).hexdigest()
        return draft

    @staticmethod
    def copies(draft):
        yield from draft.get('recommendations', {}).values()
        yield from (row['recommendation'] for row in draft.get('role_proposal', []))
        for owner, key in (('replacement', 'advice'), ('explanation', 'recommendation')):
            if key in draft.get(owner, {}):
                yield draft[owner][key]
        advice = draft.get('recommended', {}).get('advice')
        if isinstance(advice, dict):
            yield from advice.values()

    def assert_unknown(self, result, original):
        retained = result.get('retained_proposal', result)
        self.assertEqual(retained['after'], original['after'])
        self.assertEqual(retained['before'], original['before'])
        copies = list(self.copies(retained))
        self.assertTrue(copies)
        for advice in copies:
            if advice.get('cost') is not None:
                self.assertIsNone(advice['cost'].get('estimate'))
        return retained

    def test_estimate_only_costs_on_every_retention_action_and_boundary(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'rates')
            draft = deepcopy(original)
            for advice in self.copies(draft):
                advice.update(choice=None, guidance=None)
                advice.pop('withheld_evidence', None)
                advice['cost']['rates'] = None
                self.assertEqual(advice['cost']['estimate']['amount'], 20)
            self.seal(draft)
            untouched = deepcopy(draft)
            for age in (86399, 86400, 86401):
                now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00'))
                          + timedelta(seconds=age)).isoformat()
                for action in ('Explain Build', 'Back', 'Presets', 'Accept replacement',
                               ['invalid reply'], 'caller recovery Back'):
                    with self.subTest(surface=surface, age=age, action=action):
                        request = ({'state': 'blocked', 'retained_proposal': deepcopy(draft)}
                                   if action == 'caller recovery Back' else draft)
                        reply = 'Back' if action == 'caller recovery Back' else action
                        result = invoke(request, reply)
                        retained = self.assert_unknown(result, original)
                        for repeat in ('Explain Build', 'Back', 'Presets'):
                            retained = self.assert_unknown(invoke(retained, repeat), original)
                        unchanged()
                        self.assertEqual(draft, untouched)

    def test_estimate_only_with_invalid_or_expired_rate_keeps_original_evidence(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'rates')
            for rate in ([], {}, {'status': 'failed'}, original['recommendations']['implementation']['cost']['rates']):
                for age in (86399, 86400, 86401):
                    now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00'))
                              + timedelta(seconds=age)).isoformat()
                    for action in ('Explain Build', 'Back', 'Presets', 'Accept replacement', ['invalid reply']):
                        with self.subTest(surface=surface, rate=rate, age=age, action=action):
                            draft = deepcopy(original)
                            for advice in self.copies(draft):
                                advice.update(choice=None, guidance=None)
                                advice['cost']['rates'] = deepcopy(rate)
                            self.seal(draft)
                            retained = self.assert_unknown(invoke(draft, action), original)
                            self.assert_unknown(invoke(retained, 'Back'), original)
                            if isinstance(rate, dict) and rate.get('checked_at'):
                                claim = retained['recommendations']['implementation']['withheld_evidence']['rates']
                                self.assertEqual(claim['checked_at'], fixtures.NOW)
                                self.assertEqual(claim['input'], 2)
                            unchanged()

    def test_orphan_estimate_copies_are_projected_without_other_claims(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, None)
            estimate_only = {'choice': None, 'guidance': None,
                             'cost': {'rates': None, 'estimate': {'amount': 20, 'currency': 'USD'}}}
            for owner in ('replacement', 'role_proposal', 'recommended', 'explanation'):
                with self.subTest(surface=surface, owner=owner):
                    draft = deepcopy(original)
                    for advice in self.copies(draft):
                        advice.update(choice=None, guidance=None, cost=None)
                    for key in ('replacement', 'role_proposal', 'recommended', 'explanation'):
                        draft.pop(key, None)
                    draft[owner] = ({'advice': deepcopy(estimate_only)} if owner == 'replacement' else
                                    [{'recommendation': deepcopy(estimate_only)}] if owner == 'role_proposal' else
                                    {'advice': {'unknown-role': deepcopy(estimate_only)}} if owner == 'recommended' else
                                    {'recommendation': deepcopy(estimate_only)})
                    self.seal(draft)
                    result = self.assert_unknown(invoke(draft, ['invalid reply']), original)
                    self.assert_unknown(invoke(result, ['invalid reply']), original)
                    unchanged()

    def test_estimate_only_recovery_requires_explicit_refresh_or_editor(self):
        for surface in ('library', 'cli'):
            with self.subTest(surface=surface):
                invoke, now, original, unchanged = self.conversation(surface, None, keep_source=True)
                draft = deepcopy(original)
                for advice in self.copies(draft):
                    advice.update(choice=None, guidance=None)
                    advice['cost']['rates'] = None
                self.seal(draft)
                rejected = self.assert_unknown(invoke(draft, 'Accept replacement'), original)
                self.assertIn('Refresh', rejected['choices'])
                editor = invoke(rejected, 'Choose another model')
                self.assertEqual(editor['step'], 'edit')
                chosen = invoke(editor, '1')
                role = original['replacement']['role']
                self.assertEqual(chosen['after'][role]['model_id'], 'fixture-code')
                self.assertIsNone(chosen['recommendations'][role]['choice'])
                unchanged()
                refreshed = invoke(rejected, 'Refresh')
                self.assertEqual(refreshed['after'], original['after'])
                self.assertEqual(refreshed['recommendations'][role]['cost']['estimate']['amount'], 20)
                accepted = invoke(refreshed, 'Accept replacement')
                self.assertEqual(accepted['after'][role]['model_id'], 'fixture-code')
                self.assertEqual(self.state.read_bytes(), self.original)
                self.assertFalse((self.project / '.playbook-config.json').exists())

    def test_rate_metadata_alone_cannot_support_a_subtotal(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, None)
            for mutation in ({'input': None}, {'output': True}, {'currency': 'unknown'},
                             {'unit': 'unknown'}, {'billing_route': None},
                             {'model_id': 'unselected-sibling'}, {'provider': 'other'}):
                with self.subTest(surface=surface, mutation=mutation):
                    draft = deepcopy(original)
                    for advice in self.copies(draft):
                        advice['cost']['rates'].update(mutation)
                    self.seal(draft)
                    result = invoke(draft, 'Explain Build')
                    self.assert_unknown(result, original)
                    self.assertIsNotNone(result['recommendations']['implementation']['choice'])
                    unchanged()


if __name__ == '__main__':
    unittest.main()
