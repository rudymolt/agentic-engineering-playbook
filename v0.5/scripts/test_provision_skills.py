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
