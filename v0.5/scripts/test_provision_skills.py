"""Approved seam: public commands, isolated project/home and Git release fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
EDITION = SCRIPTS.parent
CLI = SCRIPTS / 'provision-skills.py'
NAMES = {
    'grill-with-docs', 'grilling', 'domain-modeling', 'to-spec', 'to-tickets',
    'tdd', 'codebase-design', 'diagnosing-bugs', 'code-review',
    'setup-matt-pocock-skills', 'writing-for-agents',
}


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class ProvisionSkillsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.home = self.root / 'home'
        self.project.mkdir()
        self.home.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.source = self.root / 'release'
        target = self.source / 'v0.5'
        target.mkdir(parents=True)
        for name in ('upstream-skills.json', 'upstream-integrations.json'):
            shutil.copy2(EDITION / name, target / name)
        if (EDITION / 'bundles').exists():
            shutil.copytree(EDITION / 'bundles', target / 'bundles')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@users.noreply.github.com')
        self.git('add', '.')
        self.git('commit', '-qm', 'Fixture release')
        self.git('tag', '-a', 'v0.5.999', '-m', 'Fixture release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/v0.5.999')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args],
                                       text=True, env=self.env).strip()

    def command(self, action, *extra, candidate=False, code=0):
        args = [sys.executable, str(CLI), '--source', str(self.source),
                '--project', str(self.project)]
        args += ['--candidate'] if candidate else [
            '--release', 'v0.5.999', '--tag-object', self.tag, '--commit', self.commit]
        result = subprocess.run([*args, action, *extra], capture_output=True,
                                text=True, env=self.env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def change_bundle(self, remove=None):
        import hashlib
        path = self.source / 'v0.5/bundles/mattpocock-skills/tdd/tests.md'
        path.write_bytes(path.read_bytes() + b'\nReviewed fixture update\n')
        manifest_path = path.parent.parent / 'integrity.json'
        manifest = json.loads(manifest_path.read_text())
        if remove:
            registry_path = self.source / 'v0.5/upstream-skills.json'
            registry = json.loads(registry_path.read_text())
            registry['skills'][remove]['project_bundle'] = False
            registry_path.write_text(json.dumps(registry))
            shutil.rmtree(path.parent.parent / remove)
            del manifest['skills'][remove]
            manifest['files'] = {p: v for p, v in manifest['files'].items()
                                 if not p.startswith(remove + '/')}
        data = path.read_bytes()
        manifest['files']['tdd/tests.md'] = {
            'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        manifest_path.write_text(json.dumps(manifest))
        self.git('add', '.')
        self.git('commit', '-qm', 'Reviewed fixture inventory change')
        self.git('tag', '-fa', 'v0.5.999', '-m', 'New fixture release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/v0.5.999')

    def test_managed_inventory_change_and_repeat_previous_recovery(self):
        self.command('install')
        original = snapshot(self.project / '.agents/skills')
        self.change_bundle(remove='writing-for-agents')
        preview = self.command('preview')
        tdd = next(s for s in preview['skills'] if s['name'] == 'tdd')
        self.assertEqual(tdd['installation'], 'update_available')
        updated = self.command('install')
        self.assertTrue(updated['complete'])
        self.assertEqual(updated['changed'], ['tdd', 'writing-for-agents'])
        self.assertFalse((self.project / '.agents/skills/writing-for-agents').exists())
        self.assertIn('Reviewed fixture update',
                      (self.project / '.agents/skills/tdd/tests.md').read_text())
        recovered = self.command('recover')
        self.assertTrue(recovered['recovery_complete'])
        self.assertFalse(recovered['complete'])  # requested new source is not restored old source
        self.assertEqual({p: b for p, (b, _) in snapshot(self.project / '.agents/skills').items()},
                         {p: b for p, (b, _) in original.items()})
        before = snapshot(self.project)
        self.assertEqual(self.command('recover')['changed'], [])
        self.assertEqual(snapshot(self.project), before)
        self.assertTrue(self.command('install')['complete'])
        self.assertEqual(snapshot(self.home), {})

    def project_git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.project), *args],
                                       env=self.env, text=True).strip()

    def test_retained_committed_customization_survives_update_and_recreation(self):
        self.command('install')
        self.project_git('init', '-q')
        self.project_git('config', 'user.name', 'Fixture')
        self.project_git('config', 'user.email', 'fixture@users.noreply.github.com')
        custom = self.project / '.agents/skills/tdd/tests.md'
        custom.write_bytes(custom.read_bytes() + b'\nProject-owned guidance\n')
        self.project_git('add', '.agents/skills')
        self.project_git('commit', '-qm', 'Retain project skill customization')
        retained_bytes = custom.read_bytes()
        blocked = self.command('install', code=2)
        self.assertEqual(next(s for s in blocked['skills'] if s['name'] == 'tdd')['installation'], 'conflict')
        retained = self.command('retain', '--skill', 'tdd')
        tdd = next(s for s in retained['skills'] if s['name'] == 'tdd')
        self.assertEqual(tdd['installation'], 'customized')
        self.assertEqual(tdd['installed_source'], 'project-customization')
        self.assertEqual(tdd['qualification'], 'unverified')
        self.assertIsNone(tdd['embedded_compatible'])
        self.project_git('add', '.agents/.skill-provisioning/retained.json')
        self.project_git('commit', '-qm', 'Record explicit retention')
        self.change_bundle()
        self.assertTrue(self.command('install')['complete'])
        self.assertEqual(custom.read_bytes(), retained_bytes)
        clone = self.root / 'recreated'
        subprocess.run(['git', 'clone', '-q', str(self.project), str(clone)],
                       env=self.env, check=True, capture_output=True)
        self.project = clone
        self.assertFalse((clone / '.agents/.skill-provisioning/state.json').exists())
        replayed = self.command('install')
        self.assertTrue(replayed['complete'])
        self.assertEqual((clone / '.agents/skills/tdd/tests.md').read_bytes(), retained_bytes)
        self.assertEqual(next(s for s in replayed['skills'] if s['name'] == 'tdd')['installation'], 'customized')
        # Neither a later edit nor an unknown untracked addition inherits retention.
        custom = clone / '.agents/skills/tdd/tests.md'
        custom.write_bytes(retained_bytes + b'\nLater VM-only edit\n')
        before = snapshot(clone)
        refused = self.command('retain', '--skill', 'tdd', code=2)
        self.assertIn('committed', refused['error'])
        self.command('install', code=2)
        self.assertEqual(snapshot(clone), before)
        self.assertEqual(snapshot(self.home), {})

    def test_interrupted_replacement_resumes_or_recovers_without_false_completion(self):
        for boundary, action in ((1, 'recover'), (1, 'install'), (2, 'recover'), (2, 'install')):
            with self.subTest(boundary=boundary, action=action):
                self.project = self.root / f'project-{boundary}-{action}'
                self.project.mkdir()
                self.command('install')
                original = (self.project / '.agents/skills/tdd/tests.md').read_bytes()
                unaffected = snapshot(self.project / '.agents/skills/code-review')
                self.change_bundle()
                driver = self.root / 'interrupt-replacement.py'
                driver.write_text("""import os, runpy, signal, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
cli = sys.argv[2]
limit = int(sys.argv[3])
sys.argv = [cli, *sys.argv[4:]]
rename = os.rename
count = 0
def interrupt(*args, **kwargs):
    global count
    rename(*args, **kwargs)
    count += 1
    if count == limit:
        os.kill(os.getpid(), signal.SIGTERM)
with patch('os.rename', interrupt):
    runpy.run_path(cli, run_name='__main__')
""")
                result = subprocess.run([
                    sys.executable, str(driver), str(SCRIPTS), str(CLI), str(boundary),
                    '--source', str(self.source), '--project', str(self.project),
                    '--release', 'v0.5.999', '--tag-object', self.tag,
                    '--commit', self.commit, 'install'], env=self.env,
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, -15, result.stderr)
                incomplete = self.command('check', code=2)
                self.assertFalse(incomplete['complete'])
                self.assertTrue(incomplete['transaction_pending'])
                self.assertEqual(next(s for s in incomplete['skills'] if s['name'] == 'code-review')['installation'], 'installed')
                if boundary == 2 and action == 'install':
                    work = self.project / '.agents/.skill-provisioning/work'
                    outside = self.home / 'saved-work'
                    work.rename(outside)
                    work.symlink_to(outside, target_is_directory=True)
                    before = snapshot(self.home)
                    blocked = self.command('install', code=2)
                    self.assertIn('staging', blocked['error'])
                    self.assertEqual(snapshot(self.home), before)
                    self.assertTrue(work.is_symlink())
                    work.unlink()
                    outside.rename(work)
                repaired = self.command(action)
                self.assertFalse(repaired['transaction_pending'])
                material = (self.project / '.agents/skills/tdd/tests.md').read_bytes()
                if action == 'recover':
                    self.assertTrue(repaired['recovery_complete'])
                    self.assertEqual(material, original)
                    before = snapshot(self.project)
                    self.command('recover')
                    self.assertEqual(snapshot(self.project), before)
                else:
                    self.assertTrue(repaired['complete'])
                    self.assertIn(b'Reviewed fixture update', material)
                self.assertEqual(snapshot(self.project / '.agents/skills/code-review'), unaffected)
                self.assertEqual(snapshot(self.home), {})

    def test_interrupted_recovery_preserves_original_target_and_source(self):
        for boundary, pending_install in ((1, False), (2, False), (1, True)):
            with self.subTest(boundary=boundary, pending_install=pending_install):
                self.project = self.root / f'recovery-{boundary}-{pending_install}'
                self.project.mkdir()
                installed_a = self.command('install')
                original = (self.project / '.agents/skills/tdd/tests.md').read_bytes()
                unaffected = snapshot(self.project / '.agents/skills/grilling')
                self.change_bundle()
                driver = self.root / 'interrupt-recovery.py'
                driver.write_text("""import os, runpy, signal, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
cli = sys.argv[2]
limit = int(sys.argv[3])
sys.argv = [cli, *sys.argv[4:]]
rename = os.rename
count = 0
def interrupt(*args, **kwargs):
    global count
    rename(*args, **kwargs)
    count += 1
    if count == limit:
        os.kill(os.getpid(), signal.SIGTERM)
with patch('os.rename', interrupt):
    runpy.run_path(cli, run_name='__main__')
""")
                def interrupt(action, limit):
                    result = subprocess.run([
                        sys.executable, str(driver), str(SCRIPTS), str(CLI), str(limit),
                        '--source', str(self.source), '--project', str(self.project),
                        '--release', 'v0.5.999', '--tag-object', self.tag,
                        '--commit', self.commit, action], env=self.env,
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, -15, result.stderr + result.stdout)
                if pending_install:
                    interrupt('install', 2)
                else:
                    self.command('install')
                interrupt('recover', boundary)
                incomplete = self.command('check', code=2)
                self.assertTrue(incomplete['transaction_pending'])
                self.assertFalse(incomplete['complete'])
                # Later unknown material still blocks recovery without being erased.
                unknown = self.project / '.agents/skills/code-review/keep.md'
                unknown.write_bytes(b'Keep the later project addition\n')
                before = snapshot(self.project)
                self.command('recover', code=2)
                self.assertEqual(snapshot(self.project), before)
                unknown.rename(self.project / 'saved-addition.md')
                recovered = self.command('recover')
                self.assertTrue(recovered['recovery_complete'])
                self.assertFalse(recovered['transaction_pending'])
                self.assertFalse(recovered['complete'])
                self.assertEqual(recovered['recovered_source'], installed_a['source'])
                self.assertEqual((self.project / '.agents/skills/tdd/tests.md').read_bytes(), original)
                self.assertEqual(snapshot(self.project / '.agents/skills/grilling'), unaffected)
                self.assertEqual((self.project / 'saved-addition.md').read_bytes(),
                                 b'Keep the later project addition\n')
                before = snapshot(self.project)
                repeated = self.command('recover')
                self.assertEqual(repeated['changed'], [])
                self.assertEqual(repeated['recovered_source'], installed_a['source'])
                self.assertEqual(snapshot(self.project), before)
                self.assertEqual(snapshot(self.home), {})

    def test_recovery_preserves_later_and_unknown_edits_and_fallback_is_explicit(self):
        self.command('install')
        self.change_bundle()
        self.command('install')
        changed = self.project / '.agents/skills/tdd/tests.md'
        changed.write_bytes(changed.read_bytes() + b'\nLater project edit\n')
        unknown = self.project / '.agents/skills/code-review/personal.md'
        unknown.write_bytes(b'Preserve unknown project material\n')
        before = snapshot(self.project)
        blocked = self.command('recover', code=2)
        self.assertIn('later or unknown', blocked['error'])
        self.assertIn('retain', blocked['repair'])
        self.assertIn('move', blocked['repair'])
        self.assertEqual(snapshot(self.project), before)
        row = next(s for s in blocked['skills'] if s['name'] == 'code-review')
        self.assertFalse(row['embedded_compatible'])
        self.assertNotIn('fallback_selection', blocked)
        fallback = self.command('fallback', '--skill', 'code-review')
        self.assertFalse(fallback['complete'])
        self.assertEqual(fallback['fallback_selection']['skill'], 'code-review')
        self.assertIn('08-review.md', fallback['fallback_selection']['route'])
        self.assertEqual(next(s for s in fallback['skills'] if s['name'] == 'code-review')['qualification'], 'unverified')
        self.assertEqual(next(s for s in fallback['skills'] if s['name'] == 'grilling')['installation'], 'installed')
        self.assertEqual(snapshot(self.project), before)
        # Explicitly moving both conflicting additions aside permits recovery.
        changed.write_bytes(changed.read_bytes().removesuffix(b'\nLater project edit\n'))
        unknown.rename(self.project / 'saved-personal.md')
        self.assertTrue(self.command('recover')['recovery_complete'])
        self.assertEqual((self.project / 'saved-personal.md').read_bytes(), b'Preserve unknown project material\n')
        self.assertEqual(snapshot(self.home), {})

    def test_recovery_preserves_a_newly_retained_committed_edit(self):
        self.command('install')
        self.change_bundle()
        self.command('install')
        self.project_git('init', '-q')
        self.project_git('config', 'user.name', 'Fixture')
        self.project_git('config', 'user.email', 'fixture@users.noreply.github.com')
        custom = self.project / '.agents/skills/tdd/tests.md'
        custom.write_bytes(custom.read_bytes() + b'\nKeep this committed project change\n')
        self.project_git('add', '.agents/skills')
        self.project_git('commit', '-qm', 'Project customization after replacement')
        preserved = custom.read_bytes()
        self.command('retain', '--skill', 'tdd')
        self.assertTrue(self.command('recover')['recovery_complete'])
        self.assertEqual(custom.read_bytes(), preserved)
        before = snapshot(self.project)
        self.command('recover')
        self.assertEqual(snapshot(self.project), before)
        custom.write_bytes(preserved + b'Unretained later change\n')
        before = snapshot(self.project)
        self.command('recover', code=2)
        self.assertEqual(snapshot(self.project), before)

    def test_malformed_history_records_fail_as_json_without_mutation(self):
        self.command('install')
        path = self.project / '.agents/.skill-provisioning/state.json'
        original = path.read_bytes()
        examples = [[], {'schema_version': 1},
                    {'schema_version': 1, 'current': None, 'previous': None,
                     'transaction': {'action': [], 'before': None, 'after': None}},
                    {'schema_version': 1, 'current': None, 'previous': None,
                     'transaction': {'action': 'install', 'before': None,
                                     'after': {'source': {}, 'skills': {}}}},
                    {'schema_version': 1, 'current': {'source': {}, 'skills': {
                        'tdd': {'../escape': 'eA=='}}}, 'previous': None, 'transaction': None}]
        for value in examples:
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                before = snapshot(self.project)
                self.command('recover', code=2)
                self.assertEqual(snapshot(self.project), before)
        path.write_bytes(original)
        path.unlink()
        outside = self.home / 'unrelated.json'
        outside.write_bytes(original)
        path.symlink_to(outside)
        before = snapshot(self.home)
        self.command('install', code=2)
        self.assertEqual(snapshot(self.home), before)
        self.assertTrue(path.is_symlink())

    def test_changed_recovery_evidence_is_not_restored(self):
        import base64
        self.command('install')
        old = (self.project / '.agents/skills/tdd/tests.md').read_bytes()
        self.change_bundle()
        self.command('install')
        path = self.project / '.agents/.skill-provisioning/state.json'
        # Simulate corruption of saved bytes with still-valid JSON/base64.
        original = path.read_text()
        damaged = original.replace(json.dumps(base64.b64encode(old).decode()),
                                   json.dumps(base64.b64encode(b'Damaged saved material').decode()))
        self.assertNotEqual(damaged, original)
        path.write_text(damaged)
        before = snapshot(self.project)
        blocked = self.command('recover', code=2)
        self.assertIn('integrity', blocked['error'])
        self.assertEqual(snapshot(self.project), before)

    def test_complete_inventory_preview_install_check_and_unchanged_rerun(self):
        local = self.project / '.agents/skills/whats-next/SKILL.md'
        local.parent.mkdir(parents=True)
        local.write_text('Existing playbook-owned skill\n')
        before = snapshot(self.project)
        preview = self.command('preview')
        self.assertEqual({s['name'] for s in preview['skills']}, NAMES)
        self.assertEqual(snapshot(self.project), before)
        self.assertFalse(preview['complete'])
        self.assertEqual(preview['source']['kind'], 'verified-release')
        self.assertEqual(preview['source']['commit'], self.commit)
        installed = self.command('install')
        self.assertTrue(installed['complete'])
        self.assertEqual(installed['changed'], sorted(NAMES))
        self.assertEqual(snapshot(self.home), {})
        self.assertEqual(local.read_text(), 'Existing playbook-owned skill\n')
        root = self.project / '.agents/skills'
        self.assertIn('MIT License', (root / 'tdd/LICENSE').read_text())
        self.assertIn('Copyright (c) 2026 Matt Pocock', (root / 'tdd/LICENSE').read_text())
        for name in NAMES:
            self.assertTrue((root / name / 'agents/openai.yaml').is_file())
        for relative in ('tdd/tests.md', 'tdd/mocking.md', 'domain-modeling/ADR-FORMAT.md',
                         'codebase-design/DEEPENING.md', 'writing-for-agents/SKILL-MECHANICS.md',
                         'setup-matt-pocock-skills/issue-tracker-gitlab.md'):
            self.assertTrue((root / relative).is_file(), relative)
        for name in ('grill-with-docs', 'to-spec', 'to-tickets', 'setup-matt-pocock-skills'):
            self.assertIn('disable-model-invocation: true', (root / name / 'SKILL.md').read_text())
            self.assertIn('allow_implicit_invocation: false',
                          (root / name / 'agents/openai.yaml').read_text())
        review = next(s for s in installed['skills'] if s['name'] == 'code-review')
        self.assertFalse(review['embedded_compatible'])
        self.assertIn('08-review.md', review['fallback'])
        self.assertEqual(review['discovery'], 'unverified')
        self.assertEqual(review['qualification'], 'unverified')
        self.assertEqual(review['upstream']['version'], 'v1.3.1')
        self.assertEqual(review['upstream']['commit'], '24fe0ef7737efae15c87225755e9f6f5965e4888')
        self.assertEqual(next(s for s in installed['skills'] if s['name'] == 'grill-with-docs')['dependencies'],
                         ['grilling', 'domain-modeling'])
        before = snapshot(self.project)
        self.assertTrue(self.command('check')['complete'])
        self.assertEqual(self.command('install')['changed'], [])
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), {})

    def test_conflicting_unknown_and_symlinked_content_is_preserved_before_activation(self):
        conflict = self.project / '.agents/skills/tdd'
        conflict.mkdir(parents=True)
        (conflict / 'SKILL.md').write_text('My newer local skill with personal changes\n')
        (conflict / 'notes.txt').write_text('Keep unknown files\n')
        before = snapshot(self.project)
        blocked = self.command('install', code=2)
        self.assertFalse(blocked['complete'])
        self.assertIn('tdd', blocked['error'])
        self.assertIn('reconcil', blocked['repair'])
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(self.command('check', code=2)['changed'], [])
        # The entire discovery parent may redirect outside the project.
        shutil.rmtree(self.project / '.agents')
        (self.project / '.agents').symlink_to(self.home, target_is_directory=True)
        before = snapshot(self.home)
        result = self.command('install', code=2)
        self.assertIn('symbolic link', result['error'])
        self.assertEqual(snapshot(self.home), before)

    def test_damaged_bundle_and_invalid_metadata_never_activate(self):
        root = self.source / 'v0.5/bundles/mattpocock-skills'
        material = root / 'tdd/tests.md'
        original = material.read_bytes()
        material.unlink()
        missing = self.command('install', candidate=True, code=2)
        self.assertFalse(missing['complete'])
        self.assertIn('integrity', missing['error'])
        self.assertEqual(snapshot(self.project), {})
        material.write_bytes(original + b'\nchanged support material\n')
        self.command('install', candidate=True, code=2)
        material.write_bytes(original)
        metadata = root / 'to-spec/agents/openai.yaml'
        metadata.write_text(metadata.read_text().replace('policy:', 'unexpected:'))
        # Even rehashed invalid metadata must fail, independently of integrity.
        import hashlib
        manifest_path = root / 'integrity.json'
        manifest = json.loads(manifest_path.read_text())
        data = metadata.read_bytes()
        manifest['files']['to-spec/agents/openai.yaml'] = {
            'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        manifest_path.write_text(json.dumps(manifest))
        invalid = self.command('install', candidate=True, code=2)
        self.assertIn('metadata', invalid['error'])
        self.assertEqual(snapshot(self.project), {})
        self.assertEqual(snapshot(self.home), {})

    def test_interrupted_initial_activation_remains_incomplete_and_resumes(self):
        # Interrupt the process at the OS activation boundary, after the first
        # complete directory becomes visible. No product-only fault switch.
        driver = self.root / 'interrupt.py'
        driver.write_text("""import os, runpy, signal, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
cli = sys.argv[2]
sys.argv = sys.argv[2:]
rename = os.rename
def interrupt(*args, **kwargs):
    rename(*args, **kwargs)
    os.kill(os.getpid(), signal.SIGTERM)
with patch('os.rename', interrupt):
    runpy.run_path(cli, run_name='__main__')
""")
        result = subprocess.run([
            sys.executable, str(driver), str(SCRIPTS), str(CLI), '--source', str(self.source),
            '--project', str(self.project), '--release', 'v0.5.999',
            '--tag-object', self.tag, '--commit', self.commit, 'install'],
            env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, -15, result.stderr)
        check = self.command('check', code=2)
        self.assertFalse(check['complete'])
        self.assertEqual(sum(s['installation'] == 'installed' for s in check['skills']), 1)
        self.assertEqual(sum(s['installation'] == 'missing' for s in check['skills']), 10)
        self.assertIn('install', check['repair'])
        before = snapshot(self.project / '.agents/skills/code-review')
        restored = self.command('install')
        self.assertTrue(restored['complete'])
        self.assertEqual(len(restored['changed']), 10)
        self.assertEqual(snapshot(self.project / '.agents/skills/code-review'), before)
        self.assertEqual(self.command('install')['changed'], [])
        self.assertEqual(snapshot(self.home), {})

    def test_release_proof_candidate_identity_and_dependency_closure(self):
        self.git('tag', '-fa', 'v0.5.999', '-m', 'Moved tag')
        rejected = self.command('install', code=2)
        self.assertIn('recorded release proof', rejected['error'])
        self.assertEqual(snapshot(self.project), {})
        candidate = self.command('preview', candidate=True)
        self.assertEqual(candidate['source']['kind'], 'maintainer-candidate')
        self.assertIsNone(candidate['source']['release'])
        self.assertEqual(len(candidate['source']['bundle_sha256']), 64)
        registry_path = self.source / 'v0.5/upstream-skills.json'
        registry = json.loads(registry_path.read_text())
        registry['skills']['codebase-design']['project_bundle'] = False
        registry_path.write_text(json.dumps(registry))
        broken = self.command('install', candidate=True, code=2)
        self.assertIn('unbundled dependency', broken['error'])
        self.assertEqual(snapshot(self.project), {})
        self.assertEqual(snapshot(self.home), {})

    def test_malformed_source_records_return_actionable_json_without_writes(self):
        for relative, value in (
            ('upstream-skills.json', []),
            ('upstream-integrations.json', []),
            ('upstream-integrations.json', {'schema_version': 1, 'integrations': []}),
            ('bundles/mattpocock-skills/integrity.json', []),
            ('bundles/mattpocock-skills/integrity.json', {'files': []}),
            ('bundles/mattpocock-skills/integrity.json', {'files': None}),
            ('bundles/mattpocock-skills/integrity.json', {'files': 7}),
            ('upstream-integrations.json', {'schema_version': 1, 'integrations': {}}),
        ):
            path = self.source / 'v0.5' / relative
            original = path.read_bytes()
            with self.subTest(source=relative, value=value):
                try:
                    path.write_text(json.dumps(value))
                    blocked = self.command('install', candidate=True, code=2)
                    self.assertFalse(blocked['complete'])
                    self.assertTrue(blocked['error'])
                    self.assertTrue(blocked['repair'])
                    self.assertEqual(snapshot(self.project), {})
                finally:
                    path.write_bytes(original)

    def test_rehashed_duplicate_policy_and_malformed_frontmatter_are_rejected(self):
        import hashlib
        root = self.source / 'v0.5/bundles/mattpocock-skills'
        manifest_path = root / 'integrity.json'
        original_manifest = manifest_path.read_bytes()
        for relative, change in (
            ('to-spec/agents/openai.yaml', lambda s: s + 'policy: {}\n'),
            ('to-spec/SKILL.md', lambda s: s.replace('name: to-spec', 'name: "to-spec')),
        ):
            path = root / relative
            original = path.read_bytes()
            with self.subTest(source=relative):
                try:
                    data = change(original.decode()).encode()
                    path.write_bytes(data)
                    manifest = json.loads(original_manifest)
                    manifest['files'][relative] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
                    manifest_path.write_text(json.dumps(manifest))
                    blocked = self.command('install', candidate=True, code=2)
                    self.assertIn('metadata', blocked['error'])
                    self.assertEqual(snapshot(self.project), {})
                finally:
                    path.write_bytes(original)
                    manifest_path.write_bytes(original_manifest)

    def test_failed_activation_reports_the_actual_partial_installation(self):
        driver = self.root / 'fail-activation.py'
        driver.write_text("""import os, runpy, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
cli = sys.argv[2]
sys.argv = sys.argv[2:]
rename = os.rename
count = 0
def fail(*args, **kwargs):
    global count
    count += 1
    if count == 2:
        raise OSError('fixture activation failure')
    return rename(*args, **kwargs)
with patch('os.rename', fail):
    runpy.run_path(cli, run_name='__main__')
""")
        result = subprocess.run([
            sys.executable, str(driver), str(SCRIPTS), str(CLI), '--source', str(self.source),
            '--project', str(self.project), '--release', 'v0.5.999', '--tag-object', self.tag,
            '--commit', self.commit, 'install'], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report['complete'])
        self.assertEqual(report['changed'], ['code-review'])
        self.assertEqual(sum(s['installation'] == 'installed' for s in report['skills']), 1)
        self.assertEqual(sum(s['installation'] == 'missing' for s in report['skills']), 10)
        self.assertIn('fixture activation failure', report['error'])
        self.assertTrue(self.command('install')['complete'])

    def test_malformed_registry_fields_return_blocked_json(self):
        path = self.source / 'v0.5/upstream-skills.json'
        original = path.read_bytes()
        cases = [('skills', 'tdd', key, value) for key, value in (
            ('package', []), ('invocation', []), ('status', []), ('tier', []),
            ('lanes', [[]]), ('previous_names', 7),
        )] + [('packages', 'mattpocock-skills', key, value) for key, value in (
            ('kind', []), ('adoption_level', []), ('pin', {'kind': []}),
            ('install', {'method': []}), ('harness_name_pattern', {'codex': 7}),
        )]
        for section, name, key, value in cases:
            with self.subTest(section=section, key=key):
                try:
                    registry = json.loads(original)
                    registry[section][name][key] = value
                    path.write_text(json.dumps(registry))
                    blocked = self.command('install', candidate=True, code=2)
                    self.assertTrue(blocked['error'])
                    self.assertTrue(blocked['repair'])
                    self.assertFalse(blocked['complete'])
                    self.assertEqual(snapshot(self.project), {})
                finally:
                    path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
