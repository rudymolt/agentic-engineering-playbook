"""Isolation checks through existing recovery fixtures and real Git stores."""
import hashlib
import os
import subprocess
import shutil
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1] / 'v0.5/delivery/tests'
sys.path.insert(0, str(TESTS))
import test_interim_recovery as recovery
from delivery_pilot.canonical import canonical_bytes


class SeedRestorationTests(unittest.TestCase):
    @staticmethod
    def template_identity(seed):
        return [(str(path.relative_to(seed.template)), path.stat().st_mode,
                 hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
                for path in sorted(seed.template.rglob('*'))]

    def test_recovery_fixture_restores_same_approved_tree_after_mutation_and_deletion(self):
        cls = recovery.RecoveryTests
        cls.setUpClass()
        first = cls('test_clean_clone_recovery_observes_active_worker_without_replacement_or_duplicate_wake')
        second = cls(first._testMethodName)
        first_active = second_active = False
        try:
            first.setUp(); first_active = True
            template_before = self.template_identity(cls._checkpoint_seed)
            self.assertTrue(all(not (path.stat().st_mode & 0o222)
                                for path in cls._checkpoint_seed.template.rglob('*')))
            original_path = first.base.root
            original_value = canonical_bytes(first.snapshot.value)
            original_identity = (first.snapshot.digest, first.snapshot.commit_sha, first.snapshot.parent_commits)
            expected_config = first.base.git('config', '--local', '--get', 'user.name', cwd=first.base.first).stdout
            # Mutate independent memory, config and filesystem objects, then
            # remove the remote entirely. None may survive a later restoration.
            first.snapshot.value['state']['next_action'] = 'corrupt-test-copy'
            first.base.git('config', 'user.name', 'Changed test copy', cwd=first.base.first)
            (first.base.first / 'stray-file').write_text('mutable working tree')
            shutil.rmtree(first.base.remote)
            first.tearDown(); first_active = False
            second.setUp(); second_active = True
            self.assertEqual(second.base.root, original_path)
            self.assertEqual(canonical_bytes(second.snapshot.value), original_value)
            self.assertEqual((second.snapshot.digest, second.snapshot.commit_sha, second.snapshot.parent_commits), original_identity)
            self.assertEqual(second.base.git('config', '--local', '--get', 'user.name', cwd=second.base.first).stdout, expected_config)
            self.assertFalse((second.base.first / 'stray-file').exists())
            approved = second.base.s2_approval()
            self.assertEqual(approved['repository']['fetch_url'], str(second.base.remote))
            clone = second.base.clone('isolated-seed-readback')
            reloaded = second.base.store(clone).reload(second.snapshot.value)
            self.assertEqual((reloaded.commit_sha, reloaded.digest, canonical_bytes(reloaded.value)),
                             (original_identity[1], original_identity[0], original_value))
            for repository in (second.base.remote, second.base.first / '.git', clone / '.git'):
                self.assertFalse((repository / 'objects/info/alternates').exists())
            self.assertEqual(self.template_identity(cls._checkpoint_seed), template_before)
            for relative in cls._checkpoint_seed.modes:
                template = cls._checkpoint_seed.template / relative
                working = second.base.root / relative
                if template.is_file():
                    self.assertNotEqual(template.stat().st_ino, working.stat().st_ino)
                    self.assertEqual(working.stat().st_nlink, 1)
        finally:
            if first_active: first.tearDown()
            if second_active: second.tearDown()
            cls.tearDownClass()

    def test_classes_own_independent_seeds_and_restore_requires_sequential_owner(self):
        classes = [recovery.RecoveryTests, recovery.RecoveryBoundaryTests]
        active = []
        try:
            for cls in classes:
                cls.setUpClass()
                case = cls(unittest.defaultTestLoader.getTestCaseNames(cls)[0])
                case.setUp()
                active.append(case)
            self.assertNotEqual(active[0].base.root, active[1].base.root)
            self.assertNotEqual(classes[0]._checkpoint_seed.template, classes[1]._checkpoint_seed.template)
            with self.assertRaisesRegex(RuntimeError, 'sequential'):
                classes[0]._checkpoint_seed.restore(recovery.recovery_repair_fixture())
            before = self.template_identity(classes[1]._checkpoint_seed)
            (active[0].base.root / 'foreign-class-mutation').write_text('independent')
            self.assertFalse((active[1].base.root / 'foreign-class-mutation').exists())
            self.assertEqual(self.template_identity(classes[1]._checkpoint_seed), before)
        finally:
            for case in reversed(active):
                case.tearDown()

    def test_fresh_workers_and_individually_selected_tests_have_independent_roots(self):
        program = '''
import sys, unittest
sys.path.insert(0, sys.argv[1])
import test_interim_recovery as recovery
cls = recovery.RecoveryTests
cls.setUpClass()
print(cls._checkpoint_seed.root, flush=True)
suite = unittest.TestSuite([cls('test_clean_clone_recovery_observes_active_worker_without_replacement_or_duplicate_wake')])
result = unittest.TextTestRunner().run(suite)
raise SystemExit(not result.wasSuccessful())
'''
        roots = []
        for _ in range(2):
            completed = subprocess.run([sys.executable, '-c', program, str(TESTS)],
                                       text=True, capture_output=True, check=True)
            roots.append(Path(completed.stdout.strip()))
        self.assertNotEqual(*roots)
        self.assertTrue(all(not root.exists() for root in roots))
