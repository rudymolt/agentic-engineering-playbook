"""Host publication through the provisioner CLI and a disposable runtime fixture."""
import json
import hashlib
from pathlib import Path
import subprocess
import shutil
import unittest

import test_gstack_runtime as runtime_tests


class GstackActivationTest(unittest.TestCase):
    setUp = runtime_tests.GstackRuntimeTest.setUp
    write = runtime_tests.GstackRuntimeTest.write
    git = runtime_tests.GstackRuntimeTest.git
    command = runtime_tests.GstackRuntimeTest.command
    pack_bun = runtime_tests.GstackRuntimeTest.pack_bun
    runtime_command = runtime_tests.GstackRuntimeTest.runtime_command
    runtime = runtime_tests.GstackRuntimeTest.runtime

    def activate(self, action='install-gstack', code=0):
        result = subprocess.run(self.runtime_command(action), env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_publish_both_host_inventories_replay_and_recover(self):
        self.runtime()
        preview = self.activate('preview-gstack')
        self.assertFalse(preview['complete'])
        self.assertFalse((self.project / '.agents').exists())
        installed = self.activate()
        self.assertTrue(installed['complete'])
        self.assertEqual(installed['discovery'], 'unverified')
        self.assertEqual(installed['qualification'], 'unverified')
        self.assertTrue((self.project / '.agents/skills/gstack-review/SKILL.md').is_file())
        self.assertTrue((self.project / '.claude/skills/review/references/guide.md').is_file())
        self.assertFalse((self.project / '.agents/skills/gstack-codex').exists())
        self.assertTrue((self.project / '.claude/skills/codex/SKILL.md').is_file())
        self.assertTrue((self.project / '.agents/skills/gstack-open-gstack-browser/SKILL.md').is_file())
        self.assertFalse((self.project / '.agents/skills/gstack').exists())
        notice = (self.project / '.agents/skills/gstack-careful/SKILL.md').read_text()
        self.assertIn('unsupported', notice)
        self.assertNotIn('Safety mode is now', notice)
        before = (self.project / '.agents/skills/gstack-review/SKILL.md').stat().st_mtime_ns
        self.assertEqual(self.activate()['changed'], [])
        self.assertEqual((self.project / '.agents/skills/gstack-review/SKILL.md').stat().st_mtime_ns, before)
        self.assertTrue(self.activate('check-gstack')['complete'])
        recovered = self.activate('recover-gstack')
        self.assertTrue(recovered['recovery_complete'])
        self.assertFalse((self.project / '.agents/skills/gstack-review').exists())
        self.assertFalse((self.project / '.claude/skills/review').exists())

    def test_missing_managed_support_repairs_but_edits_and_duplicate_names_block(self):
        self.runtime()
        self.activate()
        support = self.project / '.claude/skills/review/references/guide.md'
        support.unlink()
        self.assertFalse(self.activate('check-gstack', code=2)['complete'])
        self.assertTrue(self.activate()['complete'])
        self.assertEqual(support.read_text(), 'Complete reference\n')
        support.write_text('personal edit')
        self.assertFalse(self.activate(code=2)['complete'])
        self.assertEqual(support.read_text(), 'personal edit')
        support.write_text('Complete reference\n')
        duplicate = Path(self.env['HOME']) / '.codex/skills/other-review/SKILL.md'
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text('---\nname: review\ndescription: Personal review\n---\nPreserve this.\n')
        report = self.activate(code=2)
        self.assertFalse(report['complete'])
        self.assertIn('duplicate', report['repair'])
        self.assertTrue(duplicate.is_file())

    def test_commented_yaml_name_blocks_before_publication(self):
        self.runtime()
        duplicate = Path(self.env['HOME']) / '.codex/skills/personal/SKILL.md'
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text('---\nname: "review" # personal\n---\nKeep me.\n')
        self.assertIn(str(duplicate), self.activate(code=2)['duplicates'])
        self.assertFalse((self.project / '.agents/skills/gstack-review').exists())

    def test_second_host_staging_conflict_cannot_publish_first_host(self):
        self.runtime()
        obstruction = self.project / '.playbook/gstack-history/claude/work/review'
        obstruction.parent.mkdir(parents=True)
        obstruction.write_text('preserve')
        self.activate(code=2)
        self.assertFalse((self.project / '.agents/skills/gstack-review').exists())
        self.assertEqual(obstruction.read_text(), 'preserve')

    def test_recovery_requires_the_runtime_referenced_by_restored_skills(self):
        self.runtime()
        self.activate()
        old = self.store
        self.store = self.root.resolve() / 'second-store'
        shutil.copytree(old, self.store, symlinks=True)
        self.activate()
        current = (self.project / '.agents/skills/gstack-review/SKILL.md').read_bytes()
        old.rename(self.root / 'saved-store')
        self.assertFalse(self.activate('recover-gstack', code=2)['complete'])
        self.assertEqual((self.project / '.agents/skills/gstack-review/SKILL.md').read_bytes(), current)

    def test_recovery_reports_the_restored_runtime_and_hashes(self):
        self.runtime()
        first = self.activate()
        old = self.store
        self.store = self.root.resolve() / 'second-store'
        shutil.copytree(old, self.store, symlinks=True)
        second = self.activate()
        recovered = self.activate('recover-gstack')
        self.assertEqual(recovered['runtime']['path'], first['runtime']['path'])
        self.assertEqual(recovered['requested_runtime']['path'], second['runtime']['path'])
        for row in recovered['skills']:
            if row['installation'] == 'installed':
                self.assertEqual(row['adapted_sha256'], hashlib.sha256((Path(row['path']) / 'SKILL.md').read_bytes()).hexdigest())

    def test_late_unreadable_host_retains_observable_changes(self):
        self.runtime()
        command = self.runtime_command('install-gstack')
        injection = '''import provisioning_state as h
original_apply, original_actual = h.apply, h.actual
published = False
def apply(layout, *a, **kw):
    global published
    result = original_apply(layout, *a, **kw)
    if str(h.root(layout)).endswith('/codex') and not kw.get('dry_run'):
        published = True
    return result
def actual(layout, name):
    if published and str(h.root(layout)).endswith('/claude'):
        raise OSError('unreadable host')
    return original_actual(layout, name)
h.apply, h.actual = apply, actual
'''
        command[2] = command[2].replace('runpy.run_path(', 'exec(' + repr(injection) + '); runpy.run_path(')
        run = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        report = json.loads(run.stdout)
        self.assertIn(str(self.project.resolve() / '.agents/skills/gstack-review'), report['changed'])
        self.assertTrue(report['observation_errors'])
        self.assertTrue(any(row['installation'] == 'unknown' for row in report['skills']))

    def test_recovery_after_first_host_publication_is_resumable(self):
        self.runtime()
        command = self.runtime_command('install-gstack')
        injection = ('import provisioning_state as h,os; original=h.apply; '
                     'h.apply=lambda *a,**kw: original(*a,**kw) if kw.get("dry_run") else (original(*a,**kw),os._exit(73))[0]')
        command[2] = command[2].replace('runpy.run_path(', injection + '; runpy.run_path(')
        self.assertEqual(subprocess.run(command, env=self.env, capture_output=True).returncode, 73)
        self.assertTrue(self.activate('recover-gstack')['recovery_complete'])
        self.assertFalse((self.project / '.agents/skills/gstack-review').exists())
        self.assertFalse((self.project / '.claude/skills/review').exists())

    def test_interrupted_update_rollback_resumes_saved_destination(self):
        self.runtime()
        self.activate()
        original = (self.project / '.agents/skills/gstack-review/SKILL.md').read_bytes()
        old = self.store
        self.store = self.root.resolve() / 'second-store'
        shutil.copytree(old, self.store, symlinks=True)
        self.activate()
        command = self.runtime_command('recover-gstack')
        injection = ('import provisioning_state as h,os; original=h.os.rename; '
                     'h.os.rename=lambda a,b: (original(a,b),os._exit(73))[0] '
                     'if str(b).endswith("/gstack-careful") else original(a,b)')
        command[2] = command[2].replace('runpy.run_path(', injection + '; runpy.run_path(')
        self.assertEqual(subprocess.run(command, env=self.env, capture_output=True).returncode, 73)
        self.assertTrue(self.activate('recover-gstack')['recovery_complete'])
        self.assertEqual((self.project / '.agents/skills/gstack-review/SKILL.md').read_bytes(), original)

    def test_interrupted_first_host_install_can_roll_back(self):
        self.runtime()
        command = self.runtime_command('install-gstack')
        injection = ('import provisioning_state as h,os; original=h.os.rename; '
                     'h.os.rename=lambda a,b: (original(a,b),os._exit(73))[0] '
                     'if str(b).endswith("/gstack-careful") else original(a,b)')
        command[2] = command[2].replace('runpy.run_path(', injection + '; runpy.run_path(')
        self.assertEqual(subprocess.run(command, env=self.env, capture_output=True).returncode, 73)
        self.assertTrue(self.activate('recover-gstack')['recovery_complete'])
        self.assertFalse((self.project / '.agents/skills/gstack-careful').exists())

    def test_late_second_host_failure_reports_already_published_changes(self):
        self.runtime()
        command = self.runtime_command('install-gstack')
        injection = ('import provisioning_state as h; original=h.apply; '
                     'h.apply=lambda *a,**kw: (_ for _ in ()).throw(OSError("injected late failure")) '
                     'if str(a[0].state).endswith("/claude") and not kw.get("dry_run") else original(*a,**kw)')
        command[2] = command[2].replace('runpy.run_path(', injection + '; runpy.run_path(')
        run = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        result = json.loads(run.stdout)
        self.assertFalse(result['complete'])
        self.assertIn(str(self.project.resolve() / '.agents/skills/gstack-review'), result['changed'])
        self.assertTrue(self.activate()['complete'])

    def test_update_interrupted_between_hosts_restores_the_common_starting_inventory(self):
        self.runtime()
        self.activate()
        before = {str(p.relative_to(self.project)): p.read_bytes()
                  for folder in ('.agents', '.claude') for p in (self.project / folder).rglob('*') if p.is_file()}
        original_store = self.store
        self.store = self.root.resolve() / 'second-store'
        shutil.copytree(original_store, self.store, symlinks=True)
        command = self.runtime_command('install-gstack')
        injection = ('import provisioning_state as h,os; original=h.apply; '
                     'h.apply=lambda *a,**kw: original(*a,**kw) if kw.get("dry_run") else (original(*a,**kw),os._exit(73))[0]')
        command[2] = command[2].replace('runpy.run_path(', injection + '; runpy.run_path(')
        self.assertEqual(subprocess.run(command, env=self.env, capture_output=True).returncode, 73)
        self.assertTrue(self.activate('recover-gstack')['recovery_complete'])
        after = {str(p.relative_to(self.project)): p.read_bytes()
                 for folder in ('.agents', '.claude') for p in (self.project / folder).rglob('*') if p.is_file()}
        self.assertEqual(after, before)

    def test_missing_support_repair_keeps_the_pre_update_recovery_target(self):
        self.runtime()
        self.activate()
        original = (self.project / '.agents/skills/gstack-review/SKILL.md').read_bytes()
        old = self.store
        self.store = self.root.resolve() / 'second-store'
        shutil.copytree(old, self.store, symlinks=True)
        self.activate()
        (self.project / '.claude/skills/review/references/guide.md').unlink()
        self.assertTrue(self.activate()['complete'])
        self.assertTrue(self.activate('recover-gstack')['recovery_complete'])
        self.assertEqual((self.project / '.agents/skills/gstack-review/SKILL.md').read_bytes(), original)
        self.assertTrue((self.project / '.claude/skills/review/references/guide.md').is_file())
        self.assertTrue(self.activate('recover-gstack')['recovery_complete'])
        self.assertEqual((self.project / '.agents/skills/gstack-review/SKILL.md').read_bytes(), original)

    def test_yaml_quoted_keys_and_block_names_are_duplicate_declarations(self):
        self.runtime()
        duplicate = Path(self.env['HOME']) / '.claude/skills/personal/SKILL.md'
        duplicate.parent.mkdir(parents=True)
        for declaration in ('"name": review', 'name: >-\n  review', "'name': 'review' # personal"):
            with self.subTest(declaration=declaration):
                duplicate.write_text('---\n' + declaration + '\n---\nKeep me.\n')
                self.assertIn(str(duplicate), self.activate(code=2)['duplicates'])
                self.assertFalse((self.project / '.agents/skills/gstack-review').exists())


    def test_recovery_cannot_certify_unreadable_published_endpoints(self):
        self.runtime()
        self.activate()
        command = self.runtime_command('recover-gstack')
        injection = '''import host_transaction as g, provisioning_state as h
original_apply = g.apply
original_actual = h.actual
finished = False
def apply(*a, **kw):
    global finished
    result = original_apply(*a, **kw)
    finished = True
    return result
def actual(layout, name):
    if finished:
        raise OSError('post-recovery observation failed')
    return original_actual(layout, name)
g.apply, h.actual = apply, actual
'''
        command[2] = command[2].replace('runpy.run_path(', 'exec(' + repr(injection) + '); runpy.run_path(')
        run = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        report = json.loads(run.stdout)
        self.assertTrue(report['observation_errors'])
        self.assertFalse(report['transaction_pending'])
        self.assertFalse(report['recovery_complete'])


if __name__ == '__main__':
    unittest.main()
