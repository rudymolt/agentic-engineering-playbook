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


def full_snapshot(root):
    return {str(p.relative_to(root)): (os.readlink(p) if p.is_symlink() else
                                     p.read_bytes() if p.is_file() else None,
                                     p.lstat().st_mode, p.lstat().st_mtime_ns)
            for p in (root, *root.rglob('*'))}


class ProvisionSkillsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.home = self.root / 'home'
        self.project.mkdir()
        self.home.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'PYTHONDONTWRITEBYTECODE': '1',
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
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
        result = subprocess.run([*args, *([action] if action else []), *extra], capture_output=True,
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

    def test_default_local_discovery_reports_exact_and_missing_without_writes(self):
        source = self.home / '.agents/skills/tdd'
        shutil.copytree(self.source / 'v0.5/bundles/mattpocock-skills/tdd', source)
        shutil.copy2(self.source / 'v0.5/bundles/mattpocock-skills/LICENSE', source / 'LICENSE')
        (self.project / '.playbook-config.json').write_text('{"keep": "configuration"}')
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        # No action is the local discovery default, never installation.
        report = self.command('')
        rows = {row['name']: row for row in report['local_sources']}
        self.assertEqual(rows['tdd']['status'], 'exact')
        self.assertEqual(rows['to-spec']['status'], 'missing')
        self.assertEqual(rows['tdd']['sources'][0]['version'], None)
        self.assertEqual(rows['tdd']['invocation'], 'model')
        self.assertEqual(rows['grill-with-docs']['invocation'], 'user')
        self.assertEqual(report['changed'], [])
        self.assertEqual(report['runtime_resolution'], 'unverified')
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)

    def test_local_discovery_deduplicates_aliases_and_reports_source_differences(self):
        bundled = self.source / 'v0.5/bundles/mattpocock-skills'
        for name in ('tdd', 'grilling', 'code-review'):
            target = self.home / '.agents/skills' / name
            shutil.copytree(bundled / name, target)
            shutil.copy2(bundled / 'LICENSE', target / 'LICENSE')
        alias = self.home / '.codex/skills/tdd'
        alias.parent.mkdir(parents=True)
        alias.symlink_to(self.home / '.agents/skills/tdd', target_is_directory=True)
        customized = self.home / '.agents/skills/grilling/SKILL.md'
        customized.write_bytes(customized.read_bytes() + b'\nLocal edits\n')
        shutil.copytree(bundled / 'code-review', self.project / '.agents/skills/code-review')
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        report = self.command('discover')
        rows = {row['name']: row for row in report['local_sources']}
        self.assertEqual(rows['tdd']['status'], 'exact')
        self.assertEqual(len(rows['tdd']['sources']), 1)
        self.assertEqual(rows['grilling']['status'], 'customized')
        self.assertEqual(rows['grilling']['sources'][0]['version'], None)
        self.assertEqual(rows['grilling']['sources'][0]['difference']['changed'], ['SKILL.md'])
        self.assertEqual(rows['code-review']['status'], 'duplicate')
        self.assertTrue(rows['code-review']['blocked'])
        self.assertIn('collision', rows['code-review']['repair'])
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)
        # Complete-directory aliases also deduplicate a bucketed installation.
        bucket = self.home / '.agents/skills/core/tdd'
        shutil.copytree(self.home / '.agents/skills/tdd', bucket)
        shutil.rmtree(self.home / '.agents/skills/tdd')
        alias.unlink()
        alias.symlink_to(bucket, target_is_directory=True)
        bucketed = next(r for r in self.command('discover')['local_sources'] if r['name'] == 'tdd')
        self.assertEqual(bucketed['status'], 'exact')
        self.assertEqual(len(bucketed['sources']), 1)

    def test_local_newer_revision_is_reported_without_granting_eligibility(self):
        upstream = self.home / '.agents'
        target = upstream / 'skills/tdd'
        bundled = self.source / 'v0.5/bundles/mattpocock-skills'
        shutil.copytree(bundled / 'tdd', target)
        shutil.copy2(bundled / 'LICENSE', target / 'LICENSE')
        def upstream_git(*args):
            return subprocess.check_output(['git', '-C', str(upstream), *args],
                                           env=self.env, text=True).strip()
        upstream_git('init', '-q')
        upstream_git('config', 'user.name', 'Fixture')
        upstream_git('config', 'user.email', 'fixture@users.noreply.github.com')
        upstream_git('add', '.')
        upstream_git('commit', '-qm', 'Synthetic reviewed baseline')
        baseline = upstream_git('rev-parse', 'HEAD')
        registry_path = self.source / 'v0.5/upstream-skills.json'
        registry = json.loads(registry_path.read_text())
        registry['packages']['mattpocock-skills']['pin']['commit'] = baseline
        registry_path.write_text(json.dumps(registry))
        record_path = bundled / 'integrity.json'
        record = json.loads(record_path.read_text())
        record['commit'] = baseline
        record_path.write_text(json.dumps(record))
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic upstream baseline pin')
        self.git('tag', '-fa', 'v0.5.999', '-m', 'Fixture release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/v0.5.999')
        instructions = target / 'SKILL.md'
        instructions.write_bytes(instructions.read_bytes() + b'\nReviewed upstream evolution\n')
        upstream_git('add', '.')
        upstream_git('commit', '-qm', 'Synthetic upstream successor')
        upstream_git('tag', 'v1.4.0')
        marker = target / 'monitor-was-invoked'
        monitor = upstream / '.git/hooks/discovery-monitor'
        monitor.write_text('#!/bin/sh\nprintf invoked > "' + str(marker) + '"\nprintf "token\\000"\n')
        monitor.chmod(0o755)
        upstream_git('config', 'core.fsmonitor', str(monitor))
        self.git('config', 'core.fsmonitor', str(monitor))
        before_modes = {str(p.relative_to(self.home)): (p.lstat().st_mode, p.lstat().st_mtime_ns)
                        for p in self.home.rglob('*')}
        before_home = snapshot(self.home)
        row = next(r for r in self.command('discover')['local_sources'] if r['name'] == 'tdd')
        self.assertFalse(marker.exists(), 'Discovery invoked repository fsmonitor')
        self.assertEqual({str(p.relative_to(self.home)): (p.lstat().st_mode, p.lstat().st_mtime_ns)
                          for p in self.home.rglob('*')}, before_modes)
        self.assertEqual(row['status'], 'newer')
        self.assertEqual(row['sources'][0]['version'], 'v1.4.0')
        self.assertEqual(row['sources'][0]['revision_relation'], 'newer')
        self.assertEqual(row['qualification'], 'unverified')
        self.assertEqual(snapshot(self.home), before_home)
        (upstream / '.git/info/exclude').write_text('scratch.tmp\n')
        scratch = target / 'scratch.tmp'
        scratch.write_text('Ignored local customization\n')
        ignored = next(r for r in self.command('discover')['local_sources'] if r['name'] == 'tdd')
        self.assertEqual(ignored['status'], 'customized')
        self.assertEqual(ignored['sources'][0]['difference']['added'], ['scratch.tmp'])
        scratch.unlink()
        instructions.write_bytes(instructions.read_bytes() + b'\nUncommitted customization\n')
        row = next(r for r in self.command('discover')['local_sources'] if r['name'] == 'tdd')
        self.assertEqual(row['status'], 'customized')
        self.assertEqual(row['sources'][0]['revision_relation'], 'newer')
        self.assertEqual(row['sources'][0]['version'], 'v1.4.0')

    def test_explicit_local_choice_uses_configure_and_changed_source_blocks_only_its_job(self):
        from test_playbook_config import ConfigurationFixture
        from test_custom_skill_bindings import CustomBindingTests
        fixture = ConfigurationFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        (self.project / '.playbook-state.yml').write_bytes(fixture.runtime)
        store = self.home / '.config/ai-playbook/custom-skills'
        store.mkdir(parents=True)
        source = self.home / '.agents/skills/tdd/SKILL.md'
        source.parent.mkdir(parents=True)
        source.write_text('Synthetic newer local instructions; never invoked\n')
        identity = 'custom:local-tdd'
        CustomBindingTests.prepare_audit(self, 'implementation', identity=identity,
                                        source=source, local=store)
        adapter = ("import json,sys; r=json.load(sys.stdin); "
                   "json.dump({'request_id':r['request_id'],'checked_at':r['started_at'],"
                   "'authority':'host-reported-selection','revision':'fixture-1','routes':"
                   + repr(fixture.discovery['routes']) + "},sys.stdout)")
        def configure(action, request=None, code=0):
            run = subprocess.run([sys.executable, str(SCRIPTS / 'configure-playbook.py'),
                                  '--project', str(self.project), '--now', '2026-09-29T12:00:00Z',
                                  '--discovery-command', json.dumps([sys.executable, '-c', adapter]),
                                  action], input=json.dumps(request or {}), capture_output=True,
                                 text=True, env=self.env)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            return json.loads(run.stdout)
        initial = configure('reply', {'proposal': configure('read'), 'reply': 'Edit Build'})
        preview = configure('reply', {'proposal': initial, 'reply': '1'})
        editor = configure('reply', {'proposal': preview, 'reply': 'Edit skills implementation'})
        index = next(i + 1 for i, o in enumerate(editor['skill_options'])
                     if o['binding']['source_id'] == identity)
        preview = configure('reply', {'proposal': editor, 'reply': f'Choose {index}'})
        self.assertEqual(preview['state'], 'proposal_ready')
        self.assertFalse((self.project / '.playbook-config.json').exists())
        self.assertEqual(configure('reply', {'proposal': preview, 'reply': 'Apply'})['state'], 'applied')
        saved = (self.project / '.playbook-config.json').read_bytes()
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        report = self.command('discover')
        route = report['job_routes']['implementation']
        self.assertEqual(route['routes'][0]['source_id'], identity)
        self.assertFalse(route['launched'])
        self.assertEqual(report['runtime_resolution'], 'unverified')
        self.assertEqual(configure('job-route', {'job': 'implementation', 'owner': '07'})['routes'][0]['source_id'], identity)
        self.assertEqual(configure('job-route', {'job': 'implementation', 'owner': '08'}, code=2)['state'], 'blocked')
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)
        competitor = self.home / '.codex/skills/tdd/SKILL.md'
        competitor.parent.mkdir(parents=True)
        competitor.symlink_to('SKILL.md')
        obstructed = self.command('discover')
        self.assertEqual(next(r for r in obstructed['local_sources'] if r['name'] == 'tdd')['status'], 'duplicate')
        self.assertEqual(obstructed['job_routes']['implementation']['state'], 'blocked')
        self.assertFalse(obstructed['job_routes']['specification']['launched'])
        self.assertEqual(configure('job-route', {'job': 'implementation', 'owner': '07'}, code=2)['state'], 'blocked')
        self.assertEqual((self.project / '.playbook-config.json').read_bytes(), saved)
        shutil.rmtree(competitor.parent)
        self.assertEqual(configure('job-route', {'job': 'implementation', 'owner': '07'})['routes'][0]['source_id'], identity)
        source.write_text('Changed selected source\n')
        drifted = self.command('discover')
        self.assertEqual(drifted['job_routes']['implementation']['state'], 'blocked')
        self.assertIn('manual: stage 07', drifted['job_routes']['implementation']['message'])
        self.assertFalse(drifted['job_routes']['specification']['launched'])
        self.assertEqual(configure('job-route', {'job': 'implementation', 'owner': '07'}, code=2)['state'], 'blocked')
        self.assertEqual((self.project / '.playbook-config.json').read_bytes(), saved)
        self.assertEqual((self.project / '.playbook-state.yml').read_bytes(), fixture.runtime)
        self.assertFalse((self.project / '.agents/.skill-provisioning').exists())
        editor = configure('reply', {'proposal': configure('read'), 'reply': 'Edit skills implementation'})
        index = next(i + 1 for i, o in enumerate(editor['skill_options'])
                     if o['binding']['source_id'] == 'playbook:implementation-manual')
        preview = configure('reply', {'proposal': editor, 'reply': f'Choose {index}'})
        self.assertEqual(configure('reply', {'proposal': preview, 'reply': 'Apply'})['state'], 'applied')
        fallback = configure('job-route', {'job': 'implementation', 'owner': '07'})
        self.assertEqual(fallback['routes'][0]['source_id'], 'playbook:implementation-manual')
        self.assertFalse(fallback['launched'])
        self.assertEqual((self.project / '.playbook-state.yml').read_bytes(), fixture.runtime)

    def test_explicit_project_activation_reports_collision_and_keeps_review_fallback(self):
        bundled = self.source / 'v0.5/bundles/mattpocock-skills'
        local = self.home / '.agents/skills/code-review'
        shutil.copytree(bundled / 'code-review', local)
        shutil.copy2(bundled / 'LICENSE', local / 'LICENSE')
        state = self.project / '.playbook-state.yml'
        state.write_text('schema_version: 3\nplaybook_release: v0.5.999\n')
        home_before = snapshot(self.home)
        state_before = state.read_bytes()
        report = self.command('discover')
        self.assertEqual(next(r for r in report['local_sources'] if r['name'] == 'code-review')['status'], 'exact')
        self.assertTrue(any('embedded' in r['reason'] for r in report['job_rejections']))
        ids = [o['binding']['source_id'] for o in report['job_options']['code_review']]
        self.assertIn('playbook:code_review-manual', ids)
        self.assertNotIn('mattpocock-skills:code-review', ids)
        self.assertFalse((self.project / '.agents/skills').exists())
        self.assertTrue(self.command('install')['complete'])
        report = self.command('discover')
        review = next(r for r in report['local_sources'] if r['name'] == 'code-review')
        self.assertEqual(review['status'], 'duplicate')
        self.assertTrue(review['blocked'])
        self.assertTrue(any('collision' in r['reason'] for r in report['job_rejections']))
        self.assertEqual(report['runtime_resolution'], 'unverified')
        self.assertEqual(snapshot(self.home), home_before)
        self.assertEqual(state.read_bytes(), state_before)
        self.assertFalse((self.project / '.playbook-config.json').exists())

    def test_unreadable_local_material_is_unknown_and_preserved_without_hiding_other_sources(self):
        bundled = self.source / 'v0.5/bundles/mattpocock-skills'
        for name in ('tdd', 'to-spec'):
            target = self.home / '.agents/skills' / name
            shutil.copytree(bundled / name, target)
            shutil.copy2(bundled / 'LICENSE', target / 'LICENSE')
        support = self.home / '.agents/skills/tdd/tests.md'
        support.unlink()
        support.symlink_to(self.home / 'unavailable-support')
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        report = self.command('discover')
        rows = {r['name']: r for r in report['local_sources']}
        self.assertEqual(rows['tdd']['status'], 'unknown')
        self.assertTrue(rows['tdd']['blocked'])
        self.assertIsNone(rows['tdd']['sources'][0]['version'])
        self.assertIn('inspect', rows['tdd']['repair'])
        self.assertEqual(rows['to-spec']['status'], 'exact')
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)
        self.assertTrue(support.is_symlink())

    def test_entry_file_alias_never_reads_its_unrelated_target_directory(self):
        unrelated = self.root / 'unrelated'
        (unrelated / 'nested').mkdir(parents=True)
        (unrelated / 'readme.txt').write_text('Not a skill\n')
        (unrelated / 'sibling.txt').write_text('Synthetic unrelated record\n')
        (unrelated / 'nested/record.txt').write_text('Synthetic nested record\n')
        entry = self.home / '.agents/skills/tdd/SKILL.md'
        entry.parent.mkdir(parents=True)
        entry.symlink_to(unrelated / 'readme.txt')
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        # Audit events prove no recursive enumeration or read of the unrelated
        # tree, rather than merely asserting its names were hidden in JSON.
        wrapper = """
import os, pathlib, runpy, sys
blocked = pathlib.Path(sys.argv[1])
cli = sys.argv[2]
sys.path.insert(0, str(pathlib.Path(cli).parent))
sys.argv = sys.argv[2:]
def audit(event, args):
    if event in ('open', 'os.scandir', 'os.listdir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
        target = pathlib.Path(os.fsdecode(args[0]))
        if (target == blocked or blocked in target.parents
                or target.name in {'unrelated', 'readme.txt', 'sibling.txt', 'record.txt'}):
            raise AssertionError('discovery read unrelated source target')
sys.addaudithook(audit)
try:
    (blocked / 'sibling.txt').read_bytes()
except AssertionError:
    pass
else:
    raise AssertionError('audit read-denial control failed')
runpy.run_path(cli, run_name='__main__')
"""
        run = subprocess.run([sys.executable, '-c', wrapper, str(unrelated), str(CLI),
                              '--source', str(self.source), '--project', str(self.project),
                              '--release', 'v0.5.999', '--tag-object', self.tag,
                              '--commit', self.commit, 'discover'], capture_output=True,
                             text=True, env=self.env)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        row = next(r for r in json.loads(run.stdout)['local_sources'] if r['name'] == 'tdd')
        self.assertEqual(row['status'], 'unknown')
        self.assertTrue(row['blocked'])
        self.assertIsNone(row['sources'][0]['integrity'])
        self.assertIn('entry', row['repair'])
        self.assertNotIn(str(unrelated), run.stdout)
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)

    def test_malformed_entrypoints_remain_visible_without_hiding_healthy_sources(self):
        bundled = self.source / 'v0.5/bundles/mattpocock-skills'
        healthy = self.home / '.agents/skills/tdd'
        shutil.copytree(bundled / 'tdd', healthy)
        shutil.copy2(bundled / 'LICENSE', healthy / 'LICENSE')
        directory = healthy.parent / 'code-review'
        for kind in ('entry-cycle', 'entry-dangling', 'directory-cycle', 'directory-dangling',
                     'entry-denied', 'directory-denied'):
            with self.subTest(kind=kind):
                if kind.startswith('directory-') and kind != 'directory-denied':
                    directory.symlink_to('code-review' if kind == 'directory-cycle' else 'absent-target',
                                         target_is_directory=True)
                else:
                    directory.mkdir()
                    entry = directory / 'SKILL.md'
                    if kind.startswith('entry-') and kind not in ('entry-denied',):
                        entry.symlink_to('SKILL.md' if kind == 'entry-cycle' else 'absent.md')
                    else:
                        entry.write_bytes((bundled / 'code-review/SKILL.md').read_bytes())
                denied = directory if kind == 'directory-denied' else directory / 'SKILL.md'
                if kind.endswith('denied'):
                    denied.chmod(0)
                    try:
                        denied.open('rb') if kind == 'entry-denied' else list(denied.iterdir())
                    except PermissionError:
                        pass
                    else:
                        denied.chmod(0o700 if denied == directory else 0o600)
                        shutil.rmtree(directory)
                        self.skipTest('effective process bypasses ordinary fixture DAC denial')
                before = (denied.lstat().st_mode, denied.lstat().st_mtime_ns) if kind.endswith('denied') else None
                try:
                    report = self.command('discover')
                    rows = {r['name']: r for r in report['local_sources']}
                    self.assertEqual(rows['code-review']['status'], 'unknown')
                    self.assertTrue(rows['code-review']['blocked'])
                    self.assertTrue(rows['code-review']['repair'])
                    self.assertEqual(rows['tdd']['status'], 'exact')
                    self.assertTrue(report['job_options']['implementation'])
                    self.assertFalse(report['job_routes']['implementation']['launched'])
                    self.assertTrue(any(r['source_id'] == 'mattpocock-skills:code-review'
                                        and 'unknown' in r['reason'] for r in report['job_rejections']))
                    # The inaccessible competitor must remain visible beside
                    # a readable equal-name source instead of becoming absence.
                    shutil.copytree(bundled / 'code-review', self.project / '.agents/skills/code-review')
                    mixed = self.command('discover')
                    row = next(r for r in mixed['local_sources'] if r['name'] == 'code-review')
                    self.assertEqual(row['status'], 'duplicate')
                    self.assertTrue(row['blocked'])
                    self.assertEqual(len(row['sources']), 2)
                    self.assertTrue(any(r['source_id'] == 'mattpocock-skills:code-review'
                                        and 'collision' in r['reason'] for r in mixed['job_rejections']))
                    if before is not None:
                        self.assertEqual((denied.lstat().st_mode, denied.lstat().st_mtime_ns), before)
                finally:
                    if kind.endswith('denied'):
                        denied.chmod(0o700 if denied == directory else 0o600)
                    if directory.is_symlink():
                        directory.unlink()
                    else:
                        shutil.rmtree(directory)
                    shutil.rmtree(self.project / '.agents', ignore_errors=True)

    def test_inaccessible_supporting_directory_is_unknown_until_enumeration_is_restored(self):
        bundled = self.source / 'v0.5/bundles/mattpocock-skills'
        for name in ('tdd', 'to-spec'):
            target = self.home / '.agents/skills' / name
            shutil.copytree(bundled / name, target)
            shutil.copy2(bundled / 'LICENSE', target / 'LICENSE')
        support = self.home / '.agents/skills/tdd/agents'
        expected = (support / 'openai.yaml').read_bytes()
        before_project, before_home = snapshot(self.project), snapshot(self.home)
        before_metadata = {str(p.relative_to(self.home)): (p.lstat().st_mode, p.lstat().st_mtime_ns)
                           for p in self.home.rglob('*')}
        readable_mode = support.stat().st_mode & 0o777
        try:
            # Execute/search access keeps the known file directly readable;
            # directory listing itself must fail, as in the reported defect.
            support.chmod(0o111)
            self.assertTrue((support / 'openai.yaml').is_file())
            self.assertEqual((support / 'openai.yaml').read_bytes(), expected)
            try:
                list(support.iterdir())
            except PermissionError:
                pass
            else:
                self.skipTest('effective process bypasses supporting-directory DAC denial')
            denied_metadata = (support.lstat().st_mode, support.lstat().st_mtime_ns)
            report = self.command('')
            rows = {r['name']: r for r in report['local_sources']}
            self.assertEqual(rows['tdd']['status'], 'unknown')
            self.assertTrue(rows['tdd']['blocked'])
            self.assertIn('inspect', rows['tdd']['repair'])
            self.assertIn('enumeration', rows['tdd']['repair'])
            self.assertIsNone(rows['tdd']['sources'][0]['integrity'])
            self.assertIsNone(rows['tdd']['sources'][0]['difference'])
            self.assertEqual(rows['to-spec']['status'], 'exact')
            self.assertTrue(report['job_options']['implementation'])
            self.assertFalse(report['job_routes']['specification']['launched'])
            self.assertEqual(report['changed'], [])
            self.assertEqual((support.lstat().st_mode, support.lstat().st_mtime_ns), denied_metadata)
        finally:
            support.chmod(readable_mode)
        control = next(r for r in self.command('')['local_sources'] if r['name'] == 'tdd')
        self.assertEqual(control['status'], 'exact')
        self.assertIn('agents/openai.yaml', control['sources'][0]['integrity'])
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual({str(p.relative_to(self.home)): (p.lstat().st_mode, p.lstat().st_mtime_ns)
                          for p in self.home.rglob('*')}, before_metadata)

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
        self.assertEqual(snapshot(clone), before)
        self.command('install', code=2)
        after = snapshot(clone)
        record = '.agents/.skill-provisioning/state.json'
        self.assertEqual({p: v for p, v in after.items() if p != record},
                         {p: v for p, v in before.items() if p != record})
        before = full_snapshot(clone)
        self.assertEqual(self.command('install', code=2)['changed'], [])
        self.assertEqual(full_snapshot(clone), before)
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

    def test_later_edit_to_installed_skill_refuses_install_and_keeps_recovery_history(self):
        self.command('install')
        original = snapshot(self.project / '.agents/skills')
        self.change_bundle()
        self.command('install')
        state = self.project / '.agents/.skill-provisioning/state.json'
        recorded = state.read_bytes()
        edited = self.project / '.agents/skills/grilling/SKILL.md'
        edited.write_bytes(edited.read_bytes() + b'\nLater VM-only edit\n')
        before = snapshot(self.project)
        blocked = self.command('install', code=2)
        self.assertIn('grilling', blocked['error'])
        self.assertEqual(state.read_bytes(), recorded)
        self.assertEqual(snapshot(self.project), before)
        edited.write_bytes(edited.read_bytes().removesuffix(b'\nLater VM-only edit\n'))
        self.assertTrue(self.command('recover')['recovery_complete'])
        self.assertEqual({p: b for p, (b, _) in snapshot(self.project / '.agents/skills').items()},
                         {p: b for p, (b, _) in original.items()})

    def test_completing_a_partial_upgrade_keeps_the_pre_upgrade_recovery_target(self):
        first = self.commit
        self.change_bundle(remove='writing-for-agents')
        self.command('install')
        upgraded_from = (self.project / '.agents/skills/tdd/tests.md').read_bytes()
        own = self.project / '.agents/skills/writing-for-agents'
        own.mkdir()
        (own / 'SKILL.md').write_text('Project-owned skill\n')
        self.git('checkout', first, '--', 'v0.5/bundles', 'v0.5/upstream-skills.json')
        self.git('commit', '-qam', 'Restore the skill and earlier tdd')
        self.git('tag', '-fa', 'v0.5.999', '-m', 'Next fixture release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/v0.5.999')
        partial = self.command('install', code=2)
        self.assertEqual(next(s for s in partial['skills'] if s['name'] == 'writing-for-agents')['installation'], 'conflict')
        own.rename(self.project / 'saved-writing-for-agents')
        self.assertTrue(self.command('install')['complete'])
        self.assertTrue(self.command('recover')['recovery_complete'])
        self.assertEqual((self.project / '.agents/skills/tdd/tests.md').read_bytes(), upgraded_from)
        self.assertFalse((self.project / '.agents/skills/writing-for-agents').exists())
        self.assertEqual((self.project / 'saved-writing-for-agents/SKILL.md').read_text(), 'Project-owned skill\n')

    def test_rolled_back_interrupted_completion_keeps_the_pre_upgrade_recovery_target(self):
        first = self.commit
        self.change_bundle(remove='writing-for-agents')
        self.command('install')
        upgraded_from = (self.project / '.agents/skills/tdd/tests.md').read_bytes()
        own = self.project / '.agents/skills/writing-for-agents'
        own.mkdir()
        (own / 'SKILL.md').write_text('Project-owned skill\n')
        self.git('checkout', first, '--', 'v0.5/bundles', 'v0.5/upstream-skills.json')
        self.git('commit', '-qam', 'Restore the skill and earlier tdd')
        self.git('tag', '-fa', 'v0.5.999', '-m', 'Next fixture release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/v0.5.999')
        self.command('install', code=2)
        own.rename(self.project / 'saved-writing-for-agents')
        driver = self.root / 'interrupt-completion.py'
        driver.write_text("""import os, runpy, signal, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
cli = sys.argv[2]
sys.argv = [cli, *sys.argv[3:]]
rename = os.rename
def interrupt(*args, **kwargs):
    rename(*args, **kwargs)
    os.kill(os.getpid(), signal.SIGTERM)
with patch('os.rename', interrupt):
    runpy.run_path(cli, run_name='__main__')
""")
        result = subprocess.run([sys.executable, str(driver), str(SCRIPTS), str(CLI),
                                 '--source', str(self.source), '--project', str(self.project),
                                 '--release', 'v0.5.999', '--tag-object', self.tag,
                                 '--commit', self.commit, 'install'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, -15, result.stderr)
        self.assertTrue(self.command('recover')['recovery_complete'])
        self.assertFalse((self.project / '.agents/skills/writing-for-agents').exists())
        self.assertTrue(self.command('install')['complete'])
        self.assertTrue(self.command('recover')['recovery_complete'])
        self.assertEqual((self.project / '.agents/skills/tdd/tests.md').read_bytes(), upgraded_from)
        self.assertEqual((self.project / 'saved-writing-for-agents/SKILL.md').read_text(), 'Project-owned skill\n')

    def test_abandoned_completion_repeat_keeps_target_and_owned_skill(self):
        first = self.commit
        self.change_bundle(remove='writing-for-agents')
        self.command('install')
        upgraded_from = (self.project / '.agents/skills/tdd/tests.md').read_bytes()
        own = self.project / '.agents/skills/writing-for-agents'
        own.mkdir()
        (own / 'SKILL.md').write_text('Project-owned skill\n')
        self.git('checkout', first, '--', 'v0.5/bundles', 'v0.5/upstream-skills.json')
        self.git('commit', '-qam', 'Restore the skill and earlier tdd')
        self.git('tag', '-fa', 'v0.5.999', '-m', 'Next fixture release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/v0.5.999')
        self.command('install', code=2)
        saved = self.project / 'saved-writing-for-agents'
        own.rename(saved)
        driver = self.root / 'interrupt-completion.py'
        driver.write_text("""import os, runpy, signal, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
cli = sys.argv[2]
sys.argv = [cli, *sys.argv[3:]]
rename = os.rename
def interrupt(*args, **kwargs):
    rename(*args, **kwargs)
    os.kill(os.getpid(), signal.SIGTERM)
with patch('os.rename', interrupt):
    runpy.run_path(cli, run_name='__main__')
""")
        result = subprocess.run([sys.executable, str(driver), str(SCRIPTS), str(CLI),
                                 '--source', str(self.source), '--project', str(self.project),
                                 '--release', 'v0.5.999', '--tag-object', self.tag,
                                 '--commit', self.commit, 'install'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, -15, result.stderr)
        self.assertTrue(self.command('recover')['recovery_complete'])
        # Abandoning the completion restores the original partial state exactly.
        saved.rename(own)
        state = self.project / '.agents/.skill-provisioning/state.json'
        recorded, before = state.read_bytes(), snapshot(self.project)
        self.assertEqual(self.command('install', code=2)['changed'], [])
        self.assertEqual((state.read_bytes(), snapshot(self.project)), (recorded, before))
        self.assertTrue(self.command('recover')['recovery_complete'])
        self.assertEqual((self.project / '.agents/skills/tdd/tests.md').read_bytes(), upgraded_from)
        self.assertEqual((own / 'SKILL.md').read_text(), 'Project-owned skill\n')

    def test_skill_absent_after_recovery_is_isolated_like_a_fresh_one(self):
        self.command('install')
        self.command('recover')
        self.assertFalse((self.project / '.agents/skills/tdd').exists())
        own = self.project / '.agents/skills/tdd'
        own.mkdir()
        (own / 'SKILL.md').write_text('Project-owned tdd\n')
        partial = self.command('install', code=2)
        self.assertNotIn('error', partial)
        self.assertEqual(next(s for s in partial['skills'] if s['name'] == 'tdd')['installation'], 'conflict')
        self.assertTrue((self.project / '.agents/skills/grilling/SKILL.md').is_file())
        self.assertEqual((own / 'SKILL.md').read_text(), 'Project-owned tdd\n')

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

    def test_fresh_conflict_is_withheld_while_complete_skills_install_and_later_finish(self):
        for repair in ('retain', 'move'):
            with self.subTest(repair=repair):
                self.project = self.root / ('fresh-' + repair)
                self.project.mkdir()
                bundled = self.source / 'v0.5/bundles/mattpocock-skills'
                conflict = self.project / '.agents/skills/tdd'
                shutil.copytree(bundled / 'tdd', conflict)
                shutil.copy2(bundled / 'LICENSE', conflict / 'LICENSE')
                custom = conflict / 'tests.md'
                custom.write_bytes(custom.read_bytes() + b'\nCommitted project guidance\n')
                custom.chmod(0o640)
                self.project_git('init', '-q')
                self.project_git('config', 'user.name', 'Fixture')
                self.project_git('config', 'user.email', 'fixture@users.noreply.github.com')
                self.project_git('add', '.')
                self.project_git('commit', '-qm', 'Fresh project customization')
                (self.home / 'keep.txt').write_bytes(b'Unrelated home content')
                preserved, home = full_snapshot(conflict), full_snapshot(self.home)
                git_before = full_snapshot(self.project / '.git')
                partial = self.command('install', code=2)
                self.assertFalse(partial['complete'])
                self.assertFalse(partial['transaction_pending'])
                self.assertEqual(set(partial['changed']), NAMES - {'tdd'})
                rows = {r['name']: r for r in partial['skills']}
                self.assertEqual(rows['tdd']['installation'], 'conflict')
                self.assertIn('retain --skill tdd', ' '.join(rows['tdd']['repair_choices']))
                self.assertIn('Move', ' '.join(rows['tdd']['repair_choices']))
                for name in NAMES - {'tdd'}:
                    self.assertEqual(rows[name]['installation'], 'installed')
                    expected = {str(p.relative_to(bundled / name)): p.read_bytes()
                                for p in (bundled / name).rglob('*') if p.is_file()}
                    expected['LICENSE'] = (bundled / 'LICENSE').read_bytes()
                    target = self.project / '.agents/skills' / name
                    self.assertEqual({p: b for p, (b, _) in snapshot(target).items()}, expected)
                self.assertEqual(full_snapshot(conflict), preserved)
                self.assertEqual(full_snapshot(self.project / '.git'), git_before)
                state_path = self.project / '.agents/.skill-provisioning/state.json'
                state = json.loads(state_path.read_text())
                self.assertEqual(set(state['current']['skills']), NAMES - {'tdd'})
                self.assertNotIn('tdd', state['previous']['skills'])
                before = full_snapshot(self.project)
                self.assertFalse(self.command('check', code=2)['complete'])
                self.assertEqual(self.command('install', code=2)['changed'], [])
                self.assertEqual(full_snapshot(self.project), before)
                if repair == 'retain':
                    self.command('retain', '--skill', 'tdd')
                else:
                    conflict.rename(self.project / 'saved-tdd')
                completed = self.command('install')
                self.assertTrue(completed['complete'])
                self.assertEqual(completed['changed'], [] if repair == 'retain' else ['tdd'])
                self.assertEqual(full_snapshot(conflict if repair == 'retain' else
                                               self.project / 'saved-tdd'), preserved)
                before = full_snapshot(self.project)
                self.assertTrue(self.command('check')['complete'])
                self.assertEqual(self.command('install')['changed'], [])
                self.assertEqual(full_snapshot(self.project), before)
                self.assertEqual(full_snapshot(self.home), home)

    def test_fresh_partial_install_recovers_without_owning_conflicts_or_erasing_later_edits(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                self.project = self.root / ('partial-' + str(interrupted))
                self.project.mkdir()
                conflict = self.project / '.agents/skills/tdd'
                bundled = self.source / 'v0.5/bundles/mattpocock-skills'
                shutil.copytree(bundled / 'tdd', conflict)
                shutil.copy2(bundled / 'LICENSE', conflict / 'LICENSE')
                custom = conflict / 'tests.md'
                custom.write_bytes(custom.read_bytes() + b'\nCommitted project guidance\n')
                custom.chmod(0o640)
                self.project_git('init', '-q')
                self.project_git('config', 'user.name', 'Fixture')
                self.project_git('config', 'user.email', 'fixture@users.noreply.github.com')
                self.project_git('add', '.')
                self.project_git('commit', '-qm', 'Fresh customization')
                preserved, home = full_snapshot(conflict), full_snapshot(self.home)
                if interrupted:
                    driver = self.root / 'interrupt-partial.py'
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
                        sys.executable, str(driver), str(SCRIPTS), str(CLI),
                        '--source', str(self.source), '--project', str(self.project),
                        '--release', 'v0.5.999', '--tag-object', self.tag,
                        '--commit', self.commit, 'install'], env=self.env,
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, -15, result.stdout + result.stderr)
                else:
                    partial = self.command('install', code=2)
                    self.assertEqual(set(partial['changed']), NAMES - {'tdd'})
                check = self.command('check', code=2)
                self.assertEqual(check['transaction_pending'], interrupted)
                self.assertEqual(full_snapshot(conflict), preserved)
                installed = next(s['name'] for s in check['skills'] if s['installation'] == 'installed')
                later = self.project / '.agents/skills' / installed / 'later.md'
                later.write_bytes(b'Preserve edits made after activation')
                later.chmod(0o640)
                before = full_snapshot(self.project)
                refused = self.command('recover', code=2)
                self.assertIn(installed, refused['error'])
                self.assertEqual(full_snapshot(self.project), before)
                saved = self.project / 'saved-later.md'
                later.rename(saved)
                saved_before = (saved.read_bytes(), saved.stat().st_mode, saved.stat().st_mtime_ns)
                recovered = self.command('recover')
                self.assertTrue(recovered['recovery_complete'])
                self.assertFalse(recovered['complete'])
                self.assertFalse(recovered['transaction_pending'])
                self.assertEqual({p.name for p in (self.project / '.agents/skills').iterdir()}, {'tdd'})
                self.assertEqual(full_snapshot(conflict), preserved)
                self.assertEqual((saved.read_bytes(), saved.stat().st_mode, saved.stat().st_mtime_ns), saved_before)
                before = full_snapshot(self.project)
                self.assertEqual(self.command('recover')['changed'], [])
                self.assertEqual(full_snapshot(self.project), before)
                self.assertEqual(set(self.command('install', code=2)['changed']), NAMES - {'tdd'})
                self.assertEqual(full_snapshot(conflict), preserved)
                self.assertEqual(full_snapshot(self.home), home)

    def test_conflicting_unknown_and_symlinked_content_is_preserved_before_activation(self):
        conflict = self.project / '.agents/skills/tdd'
        conflict.mkdir(parents=True)
        (conflict / 'SKILL.md').write_text('My newer local skill with personal changes\n')
        (conflict / 'notes.txt').write_text('Keep unknown files\n')
        before = full_snapshot(conflict)
        blocked = self.command('install', code=2)
        self.assertFalse(blocked['complete'])
        self.assertEqual(set(blocked['changed']), NAMES - {'tdd'})
        row = next(s for s in blocked['skills'] if s['name'] == 'tdd')
        self.assertEqual(row['installation'], 'conflict')
        self.assertIn('retain --skill tdd', ' '.join(row['repair_choices']))
        self.assertEqual(full_snapshot(conflict), before)
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
