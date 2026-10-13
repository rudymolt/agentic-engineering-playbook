"""Real-Git checks for disposable, synchronous checkpoint fixture maintenance."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1] / 'v0.5/delivery/tests'
sys.path.insert(0, str(TESTS))


class FixtureMaintenanceTests(unittest.TestCase):
    def git(self, *args, cwd):
        return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=True)

    def test_threshold_repack_preserves_history_and_real_transport_clone(self):
        from checkpoint_fixture_support import OwnedRemoteMaintenance
        temporary = tempfile.TemporaryDirectory()
        with temporary as directory:
            root = Path(directory)
            remote = root / 'remote.git'
            self.git('init', '--bare', str(remote), cwd=root)
            owner = OwnedRemoteMaintenance(temporary, remote, self.git, threshold=12)
            owner.configure()
            for key, expected in [('gc.auto', '0'), ('maintenance.auto', 'false'), ('receive.autogc', 'false')]:
                self.assertEqual(self.git('config', '--get', key, cwd=remote).stdout.strip(), expected)
            self.assertFalse(owner.before_clone())
            previous = None
            env = dict(os.environ, GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
            for index in range(8):
                blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], input=str(index), cwd=remote, text=True, capture_output=True, check=True)
                tree = subprocess.run(['git', 'mktree'], input=f'100644 blob {blob.stdout.strip()}\tvalue\n', cwd=remote, text=True, capture_output=True, check=True).stdout.strip()
                args = ['git', 'commit-tree', tree, '-m', str(index)] + (['-p', previous] if previous else [])
                previous = subprocess.run(args, cwd=remote, env=env, text=True, capture_output=True, check=True).stdout.strip()
            self.git('update-ref', 'refs/heads/main', previous, cwd=remote)
            before = self.git('rev-list', '--objects', '--all', cwd=remote).stdout
            self.assertTrue(owner.before_clone())
            self.assertFalse(owner.before_clone())
            self.assertEqual(before, self.git('rev-list', '--objects', '--all', cwd=remote).stdout)
            clone = root / 'readback'
            self.git('clone', '--no-local', str(remote), str(clone), cwd=root)
            self.assertEqual(before, self.git('rev-list', '--objects', '--all', cwd=clone).stdout)
            self.assertFalse((clone / '.git/objects/info/alternates').exists())

    def test_foreign_or_symlink_remote_is_rejected_before_git(self):
        from checkpoint_fixture_support import OwnedRemoteMaintenance
        temporary = tempfile.TemporaryDirectory()
        with temporary as directory, tempfile.TemporaryDirectory() as foreign:
            root = Path(directory)
            def forbidden(*args, **kwargs):
                self.fail('maintenance must not call Git for a foreign target')
            with self.assertRaises(ValueError):
                OwnedRemoteMaintenance(temporary, Path(foreign), forbidden)
            (root / 'remote.git').symlink_to(foreign, target_is_directory=True)
            with self.assertRaises(ValueError):
                OwnedRemoteMaintenance(temporary, root / 'remote.git', forbidden)
