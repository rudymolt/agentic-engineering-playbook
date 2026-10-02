"""S7 replacement conversation at the public Configure seam."""

from copy import deepcopy
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


if __name__ == '__main__':
    unittest.main()
