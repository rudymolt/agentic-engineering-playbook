"""Startup acceptance for complete, portable Playbook-owned skill trees."""
import json
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_conductor_setup as fixtures


class LocalSkillSetupTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ConductorSetupTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.adopt()

    def test_missing_managed_support_is_restored_before_complete(self):
        path = self.f.project/'.agents/skills/model-router/references/chat-prompts.md'
        expected=path.read_bytes()
        path.unlink()
        result=self.f.setup_report('0')
        self.assertTrue(result['complete'])
        self.assertTrue(path.is_file(), 'setup certified readiness with missing skill support')
        self.assertEqual(path.read_bytes(),expected)
        before=fixtures.snapshot(self.f.project)
        self.assertEqual(self.f.setup_report('0')['changed'],[])
        self.assertEqual(fixtures.snapshot(self.f.project),before)

    def test_relocated_source_preserves_customization_and_refreshes_merge_base(self):
        path=self.f.project/'.agents/skills/model-router/SKILL.md'
        path.write_text(path.read_text()+'\nProject customization retained.\n')
        old=self.f.source
        moved=self.f.root/'recovered-source'
        old.rename(moved)
        self.f.source=moved
        self.f.env['GIT_CONFIG_KEY_0']='url.'+moved.as_uri()+'.insteadOf'
        result=self.f.setup_report('0')
        self.assertTrue(result['complete'])
        text=path.read_text()
        self.assertIn(str(moved),text)
        self.assertNotIn(str(old),text)
        self.assertIn('Project customization retained.',text)
        base=self.f.project/'.playbook-base/.agents/skills/model-router/SKILL.md'
        self.assertIn(str(moved),base.read_text())
        self.assertNotIn('Project customization retained.',base.read_text())

    def test_missing_delivery_support_is_restored_under_its_recorded_lock(self):
        root=self.f.project/'.agents/skills/ai-playbook-deliver'
        lock=json.loads((root/'manifest-lock.yml').read_text())
        entry=next(e for e in lock['owned_files'] if e['path']!='SKILL.md')
        path=root/entry['path'];expected=path.read_bytes();path.unlink()
        self.assertTrue(self.f.setup_report('0')['complete'])
        self.assertTrue(path.is_file(),'setup ignored missing delivery-owned support')
        self.assertEqual(path.read_bytes(),expected)

    def test_bad_base_blocks_repair_and_preserves_customizations(self):
        path=self.f.project/'.agents/skills/model-router/references/chat-prompts.md'
        path.unlink()
        base=self.f.project/'.playbook-base/.agents/skills/model-router/references/chat-prompts.md'
        base.write_text('unexplained base edit')
        result=self.f.setup_report('0',code=2)
        self.assertFalse(result['complete'])
        self.assertFalse(path.exists())
        self.assertEqual(base.read_text(),'unexplained base edit')

if __name__=='__main__':unittest.main()
