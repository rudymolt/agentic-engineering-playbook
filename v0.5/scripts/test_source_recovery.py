"""Public launcher/provisioner seam; isolated homes, projects and Git releases."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
CLI = SCRIPTS / 'recover-playbook-source.py'


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class SourceRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.project = self.root / 'project'
        self.home.mkdir(); self.project.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'PYTHONPATH': '',
                    'PYTHONDONTWRITEBYTECODE': '1', 'GIT_CONFIG_NOSYSTEM': '1',
                    'GIT_CONFIG_GLOBAL': os.devnull}
        self.source = self.root / 'release'
        shutil.copytree(SCRIPTS.parent, self.source / 'v0.5',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@users.noreply.github.com')
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic reviewed release')
        self.git('tag', '-a', 'v0.5.999', '-m', 'Synthetic release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/v0.5.999')
        self.state = self.project / '.playbook-state.yml'
        self.state.write_text(f'schema_version: 3\nplaybook_release: v0.5.999\n'
                              f'playbook_release_tag_object: "{self.tag}"\n'
                              f'playbook_release_commit: "{self.commit}"\n'
                              'decisions:\n  preserved_setting: deliberate\n')
        (self.project / 'custom.md').write_text('Preserve project ownership\n')
        self.cache = self.root / 'cache'

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args],
                                       env=self.env, text=True).strip()

    def command(self, *extra, source=None, launcher=None, code=0):
        run = subprocess.run([sys.executable, '-B', str(launcher or CLI),
                              '--project', str(self.project), '--source', str(source or self.source),
                              '--cache-dir', str(self.cache), *extra],
                             cwd=self.root, env=self.env, text=True, capture_output=True)
        self.assertEqual(run.returncode, code, run.stdout + run.stderr)
        return json.loads(run.stdout)

    def test_exact_clean_source_reused_offline_without_rewriting_adoption(self):
        before_state = self.state.read_bytes()
        before_home = snapshot(self.home)
        report = self.command('--repository', str(self.root / 'offline'), 'install')
        self.assertTrue(report['complete'])
        self.assertEqual(report['source']['commit'], self.commit)
        self.assertEqual(report['source_resolution']['mode'], 'reused')
        self.assertFalse(self.cache.exists())
        self.assertEqual(self.state.read_bytes(), before_state)
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual((self.project / 'custom.md').read_text(), 'Preserve project ownership\n')
        installed = snapshot(self.project)
        self.assertEqual(self.command('install')['changed'], [])
        self.assertEqual(snapshot(self.project), installed)

    def test_portable_launcher_explicitly_acquires_only_the_adopted_tag(self):
        launcher = self.root / 'provision.pyz'
        pack = subprocess.run([sys.executable, str(CLI), '--write-launcher', str(launcher)],
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(pack.returncode, 0, pack.stdout + pack.stderr)
        missing = self.root / 'other-machine-source'
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        blocked = self.command(source=missing, launcher=launcher, code=2)
        self.assertIn('--acquire', blocked['repair'])
        self.assertFalse(self.cache.exists())
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)
        # A later remote HEAD/tag must not become the recovered source.
        (self.source / 'future.txt').write_text('A newer release is not adopted\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Unadopted successor')
        self.git('tag', '-a', 'v0.5.1000', '-m', 'Unadopted release')
        report = self.command('--repository', str(self.source), '--acquire', 'install',
                              source=missing, launcher=launcher)
        self.assertTrue(report['complete'])
        self.assertEqual(report['source_resolution']['mode'], 'acquired')
        self.assertEqual(report['source']['commit'], self.commit)
        self.assertEqual(report['source_resolution']['tag_object'], self.tag)
        acquired = Path(report['source_resolution']['path'])
        self.assertTrue(acquired.is_relative_to(self.cache.resolve()))
        self.assertFalse(acquired.is_relative_to(self.project.resolve()))
        self.assertFalse((acquired / 'future.txt').exists())
        self.assertEqual(self.state.read_bytes(), before_project['.playbook-state.yml'][0])
        self.assertEqual(snapshot(self.home), before_home)
        installed, cached = snapshot(self.project), snapshot(self.cache)
        repeat = self.command('--repository', str(self.root / 'offline'), '--acquire', 'install',
                              source=missing, launcher=launcher)
        self.assertEqual(repeat['source_resolution']['mode'], 'reused')
        self.assertEqual(repeat['changed'], [])
        self.assertEqual(snapshot(self.project), installed)
        self.assertEqual(snapshot(self.cache), cached)

    def test_failed_exact_recovery_preserves_customizations_and_adoption(self):
        self.command('install')
        custom = self.project / '.agents/skills/tdd/SKILL.md'
        custom.write_bytes(custom.read_bytes() + b'\nProject-owned edit\n')
        original_state = self.state.read_text()
        before_home = snapshot(self.home)
        missing = self.root / 'missing-source'
        for case in ('missing-proof', 'duplicate-proof', 'wrong-commit', 'moved-tag', 'offline'):
            with self.subTest(case=case):
                self.state.write_text(original_state)
                if case == 'missing-proof':
                    self.state.write_text(original_state.replace(self.tag, ''))
                elif case == 'duplicate-proof':
                    self.state.write_text(original_state + f'playbook_release_commit: "{self.commit}"\n')
                elif case == 'wrong-commit':
                    self.state.write_text(original_state.replace(self.commit, '0' * 40))
                elif case == 'moved-tag':
                    self.git('tag', '-fa', 'v0.5.999', '-m', 'Moved annotated object')
                before = snapshot(self.project)
                repository = self.root / 'offline' if case == 'offline' else self.source
                rejected = self.command('--repository', str(repository), '--acquire', 'install',
                                        source=missing, code=2)
                self.assertFalse(rejected['complete'])
                self.assertTrue(rejected['repair'])
                self.assertEqual(rejected['changed'], [])
                self.assertEqual(snapshot(self.project), before)
                self.assertEqual(snapshot(self.home), before_home)
                self.assertFalse(any(self.cache.glob('v0.5.*')))
                if case == 'moved-tag':
                    self.git('update-ref', 'refs/tags/v0.5.999', self.tag)
        self.state.write_text(original_state)
        # Existing dirty or wrong-revision checkouts are preserved, never reset.
        for case in ('dirty', 'wrong-tag'):
            with self.subTest(case=case):
                if case == 'dirty':
                    extra = self.source / 'do-not-remove.txt'
                    extra.write_text('Intentional source edit\n')
                else:
                    self.git('tag', '-fa', 'v0.5.999', '-m', 'Wrong local tag')
                before = snapshot(self.project)
                rejected = self.command('--acquire', 'install', code=2)
                self.assertIn('restore', rejected['repair'].lower())
                self.assertEqual(snapshot(self.project), before)
                if case == 'dirty':
                    self.assertEqual(extra.read_text(), 'Intentional source edit\n')
                    extra.unlink()
                else:
                    self.git('update-ref', 'refs/tags/v0.5.999', self.tag)

    def test_old_adopted_release_without_bundle_requires_explicit_upgrade(self):
        shutil.rmtree(self.source / 'v0.5/bundles')
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic release without bundle')
        self.git('tag', '-fa', 'v0.5.999', '-m', 'Old edition fixture')
        commit = self.git('rev-parse', 'HEAD')
        tag = self.git('rev-parse', 'refs/tags/v0.5.999')
        self.state.write_text(self.state.read_text().replace(self.commit, commit).replace(self.tag, tag))
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        rejected = self.command('--repository', str(self.source), '--acquire', 'install',
                                source=self.root / 'missing', code=2)
        self.assertIn('explicitly upgrade', rejected['repair'])
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)
        self.assertFalse(any(self.cache.glob('v0.5.*')))

    def test_discovery_cannot_acquire_and_project_cache_is_refused(self):
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        rejected = self.command('--acquire', source=self.root / 'missing', code=2)
        self.assertIn('discovery never', rejected['repair'])
        self.assertFalse(self.cache.exists())
        run = subprocess.run([sys.executable, str(CLI), '--project', str(self.project),
                              '--source', str(self.root / 'missing'), '--cache-dir',
                              str(self.project / 'source-cache'), '--repository', str(self.source),
                              '--acquire', 'install'], text=True, capture_output=True, env=self.env)
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertIn('outside', json.loads(run.stdout)['repair'])
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)

    def test_cached_source_drift_is_preserved_and_never_replaced(self):
        missing = self.root / 'missing'
        report = self.command('--repository', str(self.source), '--acquire', 'preview', source=missing)
        cached = Path(report['source_resolution']['path'])
        edit = cached / 'keep-local.txt'
        edit.write_text('Preserve later source edits\n')
        before_project, before_cache = snapshot(self.project), snapshot(self.cache)
        rejected = self.command('--repository', str(self.source), '--acquire', 'install',
                                source=missing, code=2)
        self.assertIn('clean adopted release', rejected['repair'])
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.cache), before_cache)

    def test_launcher_refresh_preserves_existing_different_bytes(self):
        launcher = self.root / 'provision.pyz'
        argv = [sys.executable, str(CLI), '--write-launcher', str(launcher)]
        first = subprocess.run(argv, capture_output=True, text=True, env=self.env)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        before = (launcher.read_bytes(), launcher.stat().st_mtime_ns)
        repeated = subprocess.run(argv, capture_output=True, text=True, env=self.env)
        self.assertEqual(repeated.returncode, 0)
        self.assertFalse(json.loads(repeated.stdout)['changed'])
        self.assertEqual((launcher.read_bytes(), launcher.stat().st_mtime_ns), before)
        launcher.write_bytes(launcher.read_bytes() + b'Project-owned launcher edit')
        customized = (launcher.read_bytes(), launcher.stat().st_mtime_ns)
        rejected = subprocess.run(argv, capture_output=True, text=True, env=self.env)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn('preserve customizations', json.loads(rejected.stdout)['repair'])
        self.assertEqual((launcher.read_bytes(), launcher.stat().st_mtime_ns), customized)

    def test_launcher_fifo_is_preserved_then_regular_export_succeeds(self):
        launcher = self.root / 'provision.pyz'
        os.mkfifo(launcher)
        before = launcher.lstat()
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        command = [sys.executable, '-B', str(CLI), '--write-launcher', str(launcher)]
        rejected = subprocess.run(command, capture_output=True, text=True,
                                  env=self.env, timeout=2)
        self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
        report = json.loads(rejected.stdout)
        self.assertIn('regular file', report['repair'])
        self.assertIn('preserve', report['repair'])
        self.assertEqual(launcher.lstat(), before)
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)
        launcher.unlink()
        restored = subprocess.run(command, capture_output=True, text=True,
                                  env=self.env, timeout=2)
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertTrue(json.loads(restored.stdout)['changed'])
        self.assertTrue(launcher.is_file())

    def test_acquired_source_preserves_conflicting_project_skill_edits(self):
        self.command('install')
        custom = self.project / '.agents/skills/tdd/SKILL.md'
        custom.write_bytes(custom.read_bytes() + b'\nPreserve unretained local edit\n')
        before = snapshot(self.project)
        rejected = self.command('--repository', str(self.source), '--acquire', 'install',
                                source=self.root / 'missing', code=2)
        self.assertEqual(rejected['source_resolution']['mode'], 'acquired')
        self.assertFalse(rejected['complete'])
        self.assertIn('conflict', rejected['error'])
        self.assertEqual(snapshot(self.project), before)

    def test_portable_proof_fifo_and_link_are_preserved_then_regular_proof_succeeds(self):
        launcher = self.root / 'provision.pyz'
        pack = subprocess.run([sys.executable, '-B', str(CLI), '--write-launcher', str(launcher)],
                              capture_output=True, text=True, env=self.env, timeout=2)
        self.assertEqual(pack.returncode, 0, pack.stdout + pack.stderr)
        original = self.state.read_bytes()
        self.state.unlink()
        linked_fifo = self.root / 'adopted-proof.pipe'
        os.mkfifo(linked_fifo)
        for linked in (False, True):
            with self.subTest(linked=linked):
                if linked:
                    self.state.symlink_to(linked_fifo)
                else:
                    os.mkfifo(self.state)
                try:
                    before_state, before_target = self.state.lstat(), linked_fifo.lstat()
                    before_project, before_home = snapshot(self.project), snapshot(self.home)
                    rejected = subprocess.run([sys.executable, '-B', str(launcher),
                                               '--project', str(self.project), '--source',
                                               str(self.source), 'preview'], capture_output=True,
                                              text=True, env=self.env, timeout=2)
                    self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
                    report = json.loads(rejected.stdout)
                    self.assertIn('regular file', report['repair'])
                    self.assertIn('restore', report['repair'])
                    self.assertEqual(self.state.lstat(), before_state)
                    self.assertEqual(linked_fifo.lstat(), before_target)
                    self.assertEqual(snapshot(self.project), before_project)
                    self.assertEqual(snapshot(self.home), before_home)
                finally:
                    self.state.unlink()
        self.state.write_bytes(original)
        self.assertTrue(self.command('install', launcher=launcher)['complete'])
        # Preserve the existing effective regular-file proof behavior through a link.
        regular = self.root / 'adopted-proof.yml'
        regular.write_bytes(original)
        self.state.unlink()
        self.state.symlink_to(regular)
        link_before, target_before = self.state.lstat(), regular.stat()
        project_before, home_before = snapshot(self.project), snapshot(self.home)
        self.assertTrue(self.command('check', launcher=launcher)['complete'])
        self.assertEqual(regular.read_bytes(), original)
        self.assertEqual(self.state.lstat(), link_before)
        self.assertEqual(regular.stat().st_mode, target_before.st_mode)
        self.assertEqual(regular.stat().st_mtime_ns, target_before.st_mtime_ns)
        self.assertEqual(snapshot(self.project), project_before)
        self.assertEqual(snapshot(self.home), home_before)


if __name__ == '__main__':
    unittest.main()
