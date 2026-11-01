"""Exercise interrupted writes and preservation at the coordinated host boundary."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import provisioning_state as h
import host_transaction as group
from host_skill_name import declared_name

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layouts = {x: h.Layout(self.root/x/'skills', self.root/'history'/x) for x in ('a','b')}
        self.record = self.root/'history'/'operation.json'
    def inventory(self, version):
        return {x: {'source': {'version': version}, 'skills': {'skill': h.encode({'SKILL.md': version.encode(), 'agents/openai.yaml': b'policy'})}} for x in self.layouts}
    def run_op(self, action, after):
        return group.apply(self.record, self.layouts, action, after, repair_missing=True)
    def test_partial_staging_retry_and_recovery(self):
        for continuation in ('install','recover'):
            with self.subTest(continuation=continuation):
                self.setUp()
                after = self.inventory('long version')
                original = Path.write_bytes
                def partial(path, data):
                    if '/next/' in str(path):
                        original(path, data[:2])
                        raise OSError('interrupted write')
                    return original(path, data)
                with patch.object(Path, 'write_bytes', partial):
                    with self.assertRaises(OSError): self.run_op('install', after)
                target = after if continuation == 'install' else group.recovery_targets(self.record, self.layouts)
                self.run_op(continuation, target)
                self.assertFalse(group.load(self.record, self.layouts)['pending'])
    def test_recovery_of_repair_with_missing_files(self):
        self.run_op('install', self.inventory('A'))
        self.run_op('install', self.inventory('B'))
        for layout in self.layouts.values(): (layout.skills/'skill/agents/openai.yaml').unlink()
        self.run_op('recover', group.recovery_targets(self.record, self.layouts))
        for layout in self.layouts.values(): self.assertEqual(h.actual(layout,'skill')['SKILL.md'], b'A')
    def test_unknown_empty_directory_is_preserved(self):
        self.run_op('install', self.inventory('A'))
        layout = self.layouts['a']
        unknown = layout.skills/'skill/unknown-empty'
        unknown.mkdir()
        (layout.skills/'skill/agents/openai.yaml').unlink()
        with self.assertRaises(ValueError): self.run_op('install', self.inventory('A'))
        self.assertTrue(unknown.is_dir())
    def test_indented_duplicate_name(self):
        try: name = declared_name('---\n  name: review\n  description: personal\n---\n')
        except ValueError: return
        self.assertEqual(name, 'review')

    def test_recover_after_second_host_repair_publication_preserves_known_empty_directories(self):
        self.run_op('install', self.inventory('A'))
        self.run_op('install', self.inventory('B'))
        for layout in self.layouts.values():
            (layout.skills/'skill/agents/openai.yaml').unlink()
        original = h.os.rename
        def interrupt(a,b):
            original(a,b)
            if Path(b) == self.layouts['b'].skills/'skill':
                raise OSError('interrupted after second host repair publication')
        with patch.object(h.os, 'rename', interrupt):
            with self.assertRaises(OSError):
                self.run_op('install', self.inventory('B'))
        self.run_op('recover', group.recovery_targets(self.record,self.layouts))
        for layout in self.layouts.values():
            self.assertEqual(h.actual(layout,'skill')['SKILL.md'], b'A')


    def test_recovered_partial_stage_does_not_block_next_install(self):
        after = self.inventory('long version')
        original = Path.write_bytes
        def partial(path, data):
            if '/next/' in str(path):
                original(path, data[:2])
                raise OSError('interrupted write')
            return original(path, data)
        with patch.object(Path, 'write_bytes', partial):
            with self.assertRaises(OSError): self.run_op('install', after)
        self.run_op('recover', group.recovery_targets(self.record, self.layouts))
        self.assertFalse(group.load(self.record, self.layouts)['pending'])
        self.run_op('install', after)
        self.assertFalse(group.load(self.record, self.layouts)['pending'])


if __name__ == '__main__': unittest.main()
