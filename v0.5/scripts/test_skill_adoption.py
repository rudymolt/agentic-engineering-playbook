"""Public bootstrap/upgrade adoption seam; disposable Git releases and homes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = 'https://github.com/' + 'rudy' + 'molt/agentic-engineering-playbook.git'


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class SkillAdoptionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.project = self.root / 'project'
        self.home = self.root / 'home'
        self.home.mkdir(); self.project.mkdir()
        shutil.copytree(ROOT / 'v0.5', self.source / 'v0.5',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(ROOT / 'LICENSE', self.source / 'LICENSE')
        self.env = {**os.environ, 'HOME': str(self.home), 'PYTHONPATH': '',
                    'PYTHONDONTWRITEBYTECODE': '1', 'GIT_CONFIG_NOSYSTEM': '1',
                    'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_TERMINAL_PROMPT': '0',
                    'GIT_CONFIG_COUNT': '1',
                    'GIT_CONFIG_KEY_0': 'url.' + self.source.as_uri() + '.insteadOf',
                    'GIT_CONFIG_VALUE_0': PUBLIC}
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@users.noreply.github.com')
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic reviewed release')
        self.git('tag', '-a', 'v0.5.999', '-m', 'Synthetic release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/v0.5.999')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args],
                                       env=self.env, text=True).strip()

    def bootstrap(self, *args, code=0, project=None):
        command = [sys.executable, '-B', str(self.source / 'v0.5/scripts/bootstrap-project.py'),
                   str(project or self.project), '--playbook-path', str(self.source),
                   '--project-name', 'Fixture', '--ui', 'no', '--ci', 'copy', *args]
        return self.run_command(command, code)

    def run_command(self, command, code=0):
        run = subprocess.run(command, env=self.env, cwd=self.root, text=True,
                             capture_output=True, timeout=45)
        self.assertEqual(run.returncode, code, run.stdout + run.stderr)
        return run

    def upgrade(self, *args, code=0):
        return self.run_command([sys.executable, '-B', str(self.source / 'v0.5/scripts/upgrade-project.py'),
                                 str(self.project), *args], code)

    def plan(self, run):
        return json.loads(next(line.split(': ', 1)[1] for line in run.stdout.splitlines()
                               if line.startswith('Skill inventory adoption: ')))

    def adoption(self):
        state = (self.project / '.playbook-state.yml').read_text()
        return json.loads(next(line.split(': ', 1)[1] for line in state.splitlines()
                               if line.startswith('skill_provisioning: ')))

    def test_bootstrap_previews_then_applies_portable_adoption_without_local_activation(self):
        (self.project / 'custom.md').write_text('Project-owned content\n')
        settings = self.project / '.conductor/settings.toml'
        settings.parent.mkdir(); settings.write_text('[scripts]\nsetup = "existing setup"\n')
        before, home = snapshot(self.project), snapshot(self.home)
        plan = self.plan(self.bootstrap('--adopt-skills'))
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), home)

        self.assertEqual(plan['source'], {'release': 'v0.5.999', 'tag_object': self.tag,
                                          'commit': self.commit})
        self.assertEqual(len(plan['inventory']), 11)
        self.assertIn('writing-for-agents', plan['inventory'])
        self.assertEqual(plan['local_policy'], 'discover')
        self.bootstrap('--adopt-skills', '--inventory-revision', plan['inventory_revision'], '--apply')
        record = self.adoption()
        self.assertEqual(record['local_policy'], 'discover')
        self.assertEqual(record['bundle_sha256'], hashlib.sha256(
            (self.source / 'v0.5/bundles/mattpocock-skills/integrity.json').read_bytes()).hexdigest())
        self.assertEqual(record['launcher'], '.playbook/provision.pyz')
        encoded = json.dumps(record)
        for private in (str(self.source), str(self.home), str(self.project)):
            self.assertNotIn(private, encoded)
        self.assertFalse((self.project / '.agents/skills/tdd').exists())
        self.assertTrue((self.project / '.agents/skills/whats-next/SKILL.md').is_file())
        self.assertEqual((self.project / 'custom.md').read_bytes(), before['custom.md'][0])
        self.assertEqual(settings.read_bytes(), before['.conductor/settings.toml'][0])
        installed = snapshot(self.project)
        self.bootstrap('--adopt-skills', '--inventory-revision', plan['inventory_revision'], '--apply')
        self.assertEqual(snapshot(self.project), installed)
        launcher = self.project / record['launcher']
        replay = self.run_command([sys.executable, '-B', str(launcher), '--project', str(self.project),
                                   '--source', str(self.source), 'install'])
        self.assertTrue(json.loads(replay.stdout)['complete'])
        self.assertEqual(self.adoption(), record)
        self.assertEqual(snapshot(self.home), home)
        # Commit the portable adoption and replay it from an independent checkout.
        for argv in (['git', '-C', str(self.project), 'init', '-q'],
                     ['git', '-C', str(self.project), 'config', 'user.name', 'Fixture'],
                     ['git', '-C', str(self.project), 'config', 'user.email', 'fixture@users.noreply.github.com'],
                     ['git', '-C', str(self.project), 'add', '.'],
                     ['git', '-C', str(self.project), 'commit', '-qm', 'Explicit fixture adoption']):
            self.run_command(argv)
        recreated = self.root / 'recreated-project'
        self.run_command(['git', 'clone', '-q', str(self.project), str(recreated)])
        state_bytes = (recreated / '.playbook-state.yml').read_bytes()
        replay = self.run_command([sys.executable, '-B', str(recreated / record['launcher']),
                                   '--project', str(recreated), '--source', str(self.root / 'absent-source'),
                                   '--cache-dir', str(self.root / 'release-cache'), '--repository',
                                   str(self.source), '--acquire', 'install'])
        self.assertTrue(json.loads(replay.stdout)['complete'])
        self.assertEqual(json.loads(replay.stdout)['source_resolution']['mode'], 'acquired')
        self.assertEqual((recreated / '.playbook-state.yml').read_bytes(), state_bytes)
        self.assertEqual((recreated / 'custom.md').read_bytes(), before['custom.md'][0])
        self.assertEqual(snapshot(self.home), home)

    def test_upgrade_adopts_without_replacing_settings_bindings_setup_or_local_skills(self):
        self.bootstrap('--apply')
        state = self.project / '.playbook-state.yml'
        state.write_text(state.read_text().replace('technical_decisions: null',
                                                   'technical_decisions: auto_recommend'))
        config = self.project / '.playbook-config.json'
        models = {role: {'model_id': 'project-' + role, 'runner': 'codex', 'reasoning': 'high'}
                  for role in ('planning', 'implementation', 'verification', 'escalated_repair')}
        models['escalated_repair'].update(trigger_unsuccessful_repairs=5, cycles_per_slice=1,
                                          scope='approved_slice', authority='diagnose_and_implement')
        bindings = {'contract_version': 1, 'jobs': {job: [{'source_id': 'custom:retained-' + job,
                    'source_sha256': '1' * 64, 'contract_sha256': '2' * 64}]
                    for job in ('alignment', 'specification', 'implementation', 'code_review', 'application_qa')}}
        config.write_text(json.dumps({'schema_version': 1, 'adopted': True,
                                      'models': models, 'skills': bindings}) + '\n')
        setup = self.project / '.conductor/settings.toml'
        setup.parent.mkdir(); setup.write_text('[scripts]\nsetup = "project setup"\n')
        local = self.project / '.agents/skills/tdd/SKILL.md'
        local.parent.mkdir(); local.write_text('Project/newer local choice; retain separately\n')
        owned = self.project / '.agents/skills/whats-next/SKILL.md'
        owned.write_text(owned.read_text() + '\nProject-owned addition\n')
        preserved = {p: p.read_bytes() for p in (config, setup, local, owned)}
        before = snapshot(self.project)
        plan = self.plan(self.upgrade('--plan', '--adopt-skills'))
        self.assertEqual(snapshot(self.project), before)
        self.upgrade('--apply-safe', '--adopt-skills', '--inventory-revision', plan['inventory_revision'])
        self.assertEqual(self.adoption()['local_policy'], 'discover')
        self.assertIn('technical_decisions: auto_recommend', state.read_text())
        self.assertIn('playbook_release: v0.5.999', state.read_text())
        for p, content in preserved.items():
            self.assertEqual(p.read_bytes(), content)
        adopted = snapshot(self.project)
        self.upgrade('--apply-safe', '--adopt-skills', '--inventory-revision', plan['inventory_revision'])
        self.assertEqual(snapshot(self.project), adopted)


    def test_linked_adoption_state_refuses_apply_without_changing_link_target_or_consumer(self):
        for mode in ('bootstrap', 'upgrade'):
            with self.subTest(mode=mode):
                self.project = self.root / (mode + '-consumer')
                self.project.mkdir()
                self.bootstrap('--apply')
                (self.project / 'custom.txt').write_text('Retained project content\n')
                preview_args = ['--adopt-skills']
                if mode == 'upgrade':
                    preview_args.insert(0, '--plan')
                preview = self.bootstrap if mode == 'bootstrap' else self.upgrade
                plan = self.plan(preview(*preview_args))
                state = self.project / '.playbook-state.yml'
                external = self.root / (mode + '-external-state.yml')
                state.rename(external)
                state.symlink_to(external)

                def endpoints():
                    link = state.lstat()
                    target = external.stat()
                    return ((os.readlink(state), link.st_mode, link.st_mtime_ns),
                            (external.read_bytes(), target.st_mode, target.st_mtime_ns),
                            snapshot(self.project), snapshot(self.home))

                before = endpoints()
                # Both the ordinary control and inventory preview remain read-only.
                if mode == 'bootstrap':
                    self.bootstrap('--apply')
                else:
                    self.upgrade('--plan')
                self.assertEqual(endpoints(), before)
                linked_plan = self.plan(preview(*preview_args))
                self.assertEqual(linked_plan, plan)
                self.assertEqual(endpoints(), before)
                command = [sys.executable, '-B', str(self.source / 'v0.5/scripts' /
                           (mode + '-project.py')), str(self.project)]
                if mode == 'bootstrap':
                    command += ['--playbook-path', str(self.source), '--project-name',
                                'Fixture', '--ui', 'no', '--ci', 'copy', '--apply']
                else:
                    command += ['--apply-safe']
                command += ['--adopt-skills', '--inventory-revision', plan['inventory_revision']]
                refused = subprocess.run(command, env=self.env, cwd=self.root, text=True,
                                         capture_output=True, timeout=45)
                self.assertEqual(endpoints(), before, refused.stdout + refused.stderr)
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn('linked adoption state', refused.stderr)
                self.assertIn('restore', refused.stderr)
                self.assertNotIn('Traceback', refused.stderr)
                self.assertFalse((self.project / '.playbook/provision.pyz').exists())
                # Explicit owner repair restores regular state; the same reviewed plan works.
                state.unlink()
                shutil.copy2(external, state)
                self.run_command(command)
                self.assertEqual(self.adoption()['local_policy'], 'discover')
                self.assertFalse(state.is_symlink())
                target = external.stat()
                self.assertEqual((external.read_bytes(), target.st_mode, target.st_mtime_ns), before[1])
                self.assertEqual(snapshot(self.home), before[3])


    def test_existing_adoption_does_not_advance_cloud_proof_without_inventory_selection(self):
        plan = self.plan(self.bootstrap('--adopt-skills'))
        self.bootstrap('--adopt-skills', '--inventory-revision', plan['inventory_revision'], '--apply')
        before = snapshot(self.project)
        (self.source / 'next-release.txt').write_text('Synthetic explicitly selectable successor\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic later reviewed release')
        self.git('tag', '-a', 'v0.5.1000', '-m', 'Synthetic successor')
        blocked = self.upgrade('--apply-safe', code=2)
        self.assertIn('--adopt-skills', blocked.stdout + blocked.stderr)
        self.assertEqual(snapshot(self.project), before)
        selected = self.plan(self.upgrade('--plan', '--adopt-skills'))
        self.upgrade('--apply-safe', '--adopt-skills', '--inventory-revision', selected['inventory_revision'])
        self.assertIn('playbook_release: v0.5.1000', (self.project / '.playbook-state.yml').read_text())
        self.assertEqual(self.adoption()['local_policy'], 'discover')


    def publish(self, tag):
        self.git('add', '.')
        self.git('commit', '--allow-empty', '-qm', 'Synthetic fixture release')
        self.git('tag', '-a', tag, '-m', 'Synthetic release')
        self.commit = self.git('rev-parse', 'HEAD')
        self.tag = self.git('rev-parse', 'refs/tags/' + tag)

    def test_reviewed_revision_and_maintainer_source_guards_preserve_all_inputs(self):
        before, home = snapshot(self.project), snapshot(self.home)
        plan = self.plan(self.bootstrap('--adopt-skills'))
        for revision in (None, '0' * 64):
            args = ['--adopt-skills', '--apply']
            if revision is not None:
                args += ['--inventory-revision', revision]
            blocked = self.bootstrap(*args, code=2)
            self.assertIn('inventory-revision', blocked.stderr)
            self.assertEqual(snapshot(self.project), before)
        rejected = self.bootstrap('--adopt-skills', project=self.source, code=2)
        self.assertIn('maintainer', rejected.stderr)
        self.assertFalse((self.source / '.playbook-state.yml').exists())
        self.git('tag', '-d', 'v0.5.999')
        blocked = self.bootstrap('--adopt-skills', code=2)
        self.assertIn('verified', blocked.stderr)
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), home)

    def test_bootstrap_required_review_does_not_adopt_or_certify(self):
        agents = self.project / 'AGENTS.md'
        agents.write_text('Project-written instructions need an explicit merge\n')
        plan = self.plan(self.bootstrap('--adopt-skills'))
        blocked = self.bootstrap('--adopt-skills', '--inventory-revision', plan['inventory_revision'],
                                 '--apply', code=2)
        self.assertIn('manual review', blocked.stdout)
        state = (self.project / '.playbook-state.yml').read_text()
        self.assertIn('playbook_version: null', state)
        self.assertIn('playbook_release: null', state)
        self.assertNotIn('skill_provisioning:', state)
        self.assertFalse((self.project / '.playbook/provision.pyz').exists())
        self.assertEqual(agents.read_text(), 'Project-written instructions need an explicit merge\n')

    def test_old_bundleless_consumer_adopts_only_after_required_upgrade_review_is_resolved(self):
        bundle = self.source / 'v0.5/bundles'
        saved = self.root / 'saved-bundles'
        shutil.copytree(bundle, saved)
        shutil.rmtree(bundle)
        self.publish('v0.5.998')
        empty = snapshot(self.project)
        self.bootstrap('--adopt-skills', code=2)
        self.assertEqual(snapshot(self.project), empty)
        self.bootstrap('--apply')
        state = self.project / '.playbook-state.yml'
        state.write_text(state.read_text().replace(next(line for line in state.read_text().splitlines()
                                                       if line.startswith('last_upgraded:')),
                                                   'last_upgraded: 2026-01-01'))
        original = snapshot(self.project)
        self.upgrade('--plan')
        self.assertEqual(snapshot(self.project), original)
        shutil.copytree(saved, bundle)
        self.publish('v0.5.1000')
        base = self.project / '.playbook-base/AGENTS.md'
        base_bytes = base.read_bytes()
        base.unlink()
        plan = self.plan(self.upgrade('--plan', '--adopt-skills'))
        refused = self.upgrade('--apply-safe', '--adopt-skills', '--inventory-revision',
                               plan['inventory_revision'], code=2)
        self.assertIn('manual review', refused.stdout)
        self.assertIn('playbook_release: v0.5.998', state.read_text())
        self.assertIn('last_upgraded: 2026-01-01', state.read_text())
        self.assertNotIn('skill_provisioning:', state.read_text())
        self.assertFalse((self.project / '.playbook/provision.pyz').exists())
        base.write_bytes(base_bytes)
        self.upgrade('--apply-safe', '--adopt-skills', '--inventory-revision', plan['inventory_revision'])
        self.assertIn('playbook_release: v0.5.1000', state.read_text())
        self.assertEqual(self.adoption()['local_policy'], 'discover')


    def test_failed_completion_preserves_linked_state_instead_of_rolling_back_its_target(self):
        self.bootstrap('--apply')
        template_state = (self.project / '.playbook-state.yml').read_text()
        status = self.source / 'v0.5/scripts/compute-status.py'
        original_status = status.read_text()
        for mode in ('bootstrap', 'upgrade'):
            with self.subTest(mode=mode):
                self.project = self.root / (mode + '-failed-consumer')
                self.project.mkdir()
                if mode == 'upgrade':
                    status.write_text(original_status)
                    self.publish('v0.5.1001')
                    self.bootstrap('--apply')
                state = self.project / '.playbook-state.yml'
                external = self.root / (mode + '-retained-state.yml')
                external.write_text(template_state + '\nskill_provisioning: null\n')
                target = external.stat()
                before = (external.read_bytes(), target.st_mode, target.st_mtime_ns)
                evidence = self.root / (mode + '-completion-endpoint.json')
                status = self.source / 'v0.5/scripts/compute-status.py'
                # A failing public completion adapter leaves a link as recovery evidence.
                # This is a serial error-path fixture, not a concurrent-writer guarantee.
                status.write_text(
                    'import json,os,sys\nfrom pathlib import Path\n'
                    'state = Path(sys.argv[1]) / ".playbook-state.yml"\n'
                    'state.unlink()\n'
                    'state.symlink_to(' + repr(str(external)) + ')\n'
                    'info = state.lstat()\n'
                    'Path(' + repr(str(evidence)) + ').write_text(json.dumps('
                    '[os.readlink(state), info.st_mode, info.st_mtime_ns]))\n'
                    'raise SystemExit(7)\n')
                self.publish('v0.5.' + ('1000' if mode == 'bootstrap' else '1002'))
                preview = self.bootstrap if mode == 'bootstrap' else self.upgrade
                args = ['--adopt-skills'] if mode == 'bootstrap' else ['--plan', '--adopt-skills']
                plan = self.plan(preview(*args))
                args = ['--apply'] if mode == 'bootstrap' else ['--apply-safe']
                failed = preview(*args, '--adopt-skills', '--inventory-revision',
                                 plan['inventory_revision'], code=1)
                target = external.stat()
                self.assertEqual((external.read_bytes(), target.st_mode, target.st_mtime_ns), before)
                self.assertTrue(state.is_symlink(), failed.stdout + failed.stderr)
                info = state.lstat()
                self.assertEqual([os.readlink(state), info.st_mode, info.st_mtime_ns],
                                 json.loads(evidence.read_text()))
                self.assertIn('Incomplete inventory recovery', failed.stderr)
                self.assertIn('linked adoption state', failed.stderr)
                self.assertIn('restore', failed.stderr)
                self.assertNotIn('Traceback', failed.stderr)
                self.assertTrue((self.project / '.playbook/provision.pyz').is_file())


    def test_failed_status_computation_cannot_advance_bootstrap_or_upgrade_adoption(self):
        fresh = self.project
        existing = self.root / 'existing-project'
        self.bootstrap('--apply', project=existing)
        old_state = (existing / '.playbook-state.yml').read_bytes()
        status = self.source / 'v0.5/scripts/compute-status.py'
        status.write_text('raise SystemExit(7)\n')
        self.publish('v0.5.1000')
        for mode, project in (('bootstrap', fresh), ('upgrade', existing)):
            with self.subTest(mode=mode):
                self.project = project
                if mode == 'bootstrap':
                    plan = self.plan(self.bootstrap('--adopt-skills'))
                    self.bootstrap('--apply', '--adopt-skills', '--inventory-revision',
                                   plan['inventory_revision'], code=1)
                else:
                    plan = self.plan(self.upgrade('--plan', '--adopt-skills'))
                    self.upgrade('--apply-safe', '--adopt-skills', '--inventory-revision',
                                 plan['inventory_revision'], code=1)
                state = (project / '.playbook-state.yml').read_text()
                self.assertNotIn('playbook_release: v0.5.1000', state)
                self.assertNotIn('skill_provisioning:', state)
                self.assertFalse((project / '.playbook/provision.pyz').exists())
                if mode == 'bootstrap':
                    self.assertIn('playbook_version: null', state)
                else:
                    self.assertIn('playbook_release: v0.5.999', state)
                    self.assertEqual((project / '.playbook-state.yml').read_bytes(), old_state)


    def test_conflicting_launcher_and_malformed_adoption_are_preserved_before_apply(self):
        launcher = self.project / '.playbook/provision.pyz'
        launcher.parent.mkdir()
        launcher.write_bytes(b'Project-owned launcher bytes')
        before = snapshot(self.project)
        refused = self.bootstrap('--adopt-skills', code=2)
        self.assertIn('preserve', refused.stderr.lower())
        self.assertEqual(snapshot(self.project), before)
        launcher.unlink()
        self.bootstrap('--apply')
        state = self.project / '.playbook-state.yml'
        original = state.read_text()
        for record in ('skill_provisioning: {"schema_version":9}',
                       'skill_provisioning : {"schema_version":9}',
                       'skill_provisioning: null\nskill_provisioning : null'):
            with self.subTest(record=record):
                state.write_text(original + '\n' + record + '\n')
                before = snapshot(self.project)
                self.bootstrap('--adopt-skills', code=2)
                self.assertEqual(snapshot(self.project), before)
        state.write_text(original)


    def test_incompatible_release_launcher_requires_reviewed_upgrade_without_writes(self):
        helper = self.source / 'v0.5/scripts/recover-playbook-source.py'
        helper.write_text(helper.read_text().replace('def launcher_bytes():', 'def unsupported_legacy_renderer():'))
        self.publish('v0.5.1000')
        before, home = snapshot(self.project), snapshot(self.home)
        blocked = self.bootstrap('--adopt-skills', code=2)
        self.assertIn('upgrade', blocked.stderr.lower())
        self.assertNotIn('Traceback', blocked.stderr)
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), home)


if __name__ == '__main__':
    unittest.main()
