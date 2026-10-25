"""Setup composition through the public launcher, in disposable projects/homes."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = 'https://github.com/' + 'rudy' + 'molt/agentic-engineering-playbook.git'


def snapshot(root):
    return {str(p.relative_to(root)): (os.readlink(p) if p.is_symlink() else
                                     p.read_bytes() if p.is_file() else None,
                                     p.lstat().st_mode, p.lstat().st_mtime_ns)
            for p in root.rglob('*')}


class ConductorSetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'release with spaces'
        self.project = self.root / 'consumer'
        self.home = self.root / 'home'
        self.project.mkdir(); self.home.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'PYTHONPATH': '',
                    'PYTHONDONTWRITEBYTECODE': '1', 'GIT_CONFIG_NOSYSTEM': '1',
                    'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_TERMINAL_PROMPT': '0',
                    'GIT_CONFIG_COUNT': '1',
                    'GIT_CONFIG_KEY_0': 'url.' + self.source.as_uri() + '.insteadOf',
                    'GIT_CONFIG_VALUE_0': PUBLIC}
        shutil.copytree(ROOT / 'v0.5', self.source / 'v0.5',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(ROOT / 'LICENSE', self.source / 'LICENSE')
        for args in (('init', '-q'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@users.noreply.github.com'),
                     ('add', '.'), ('commit', '-qm', 'Synthetic reviewed release'),
                     ('tag', '-a', 'v0.5.999', '-m', 'Synthetic release')):
            self.run_command(['git', '-C', str(self.source), *args])

    def run_command(self, command, *, env=None, cwd=None, code=0):
        run = subprocess.run(command, env=env or self.env, cwd=cwd or self.root,
                             capture_output=True, text=True, timeout=45)
        self.assertEqual(run.returncode, code, run.stdout + run.stderr)
        return run

    def setup_command(self, *extra, project=None, source=None, candidate=False):
        project = project or self.project
        entry = (self.source / 'v0.5/scripts/recover-playbook-source.py' if candidate
                 else project / '.playbook/provision.pyz')
        return [sys.executable, '-B', str(entry), '--project', str(project),
                '--source', str(source or self.source), *(['--candidate'] if candidate else []),
                *extra, 'setup']

    def setup_report(self, host, *extra, code=0, **kwargs):
        env = {**self.env, 'CONDUCTOR_IS_LOCAL': host}
        if host is None:
            del env['CONDUCTOR_IS_LOCAL']
        run = self.run_command(self.setup_command(*extra, **kwargs), env=env, code=code)
        return json.loads(run.stdout)

    def adopt(self, *extra):
        bootstrap = [sys.executable, '-B', str(self.source / 'v0.5/scripts/bootstrap-project.py'),
                     str(self.project), '--playbook-path', str(self.source),
                     '--project-name', 'Fixture', '--ui', 'no', '--ci', 'copy',
                     '--adopt-skills', *extra]
        preview = self.run_command(bootstrap)
        plan = json.loads(next(line.split(': ', 1)[1] for line in preview.stdout.splitlines()
                               if line.startswith('Skill inventory adoption: ')))
        self.run_command([*bootstrap, '--inventory-revision', plan['inventory_revision'], '--apply'])

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_explicit_setup_adoption_composes_quoted_commands_exports_and_repeats(self):
        import tomllib
        settings = self.project / '.conductor/settings.toml'
        settings.parent.mkdir()
        marker = self.root / 'prior setup; literal.txt'
        original = 'export SETUP_FIXTURE=kept\nprintf "%s\\n" "$SETUP_FIXTURE" >> ' + shlex.quote(str(marker))
        content = '# Project settings stay owned\n[scripts]\nsetup = ' + json.dumps(original) + '\nrun = "keep run"\n'
        settings.write_text(content)
        self.adopt('--conductor-setup')
        configured = settings.read_text()
        self.assertIn('# Project settings stay owned', configured)
        parsed = tomllib.loads(configured)
        self.assertEqual(parsed['scripts']['run'], 'keep run')
        self.assertTrue(parsed['scripts']['setup'].startswith(original + '\n'))
        self.assertTrue((self.project / '.playbook/conductor-setup.sh').is_file())
        before = snapshot(self.project)
        self.adopt('--conductor-setup')
        self.assertEqual(snapshot(self.project), before)
        home = snapshot(self.home)
        for host in ('1', '0'):
            run = self.run_command([shutil.which('sh'), '-c', parsed['scripts']['setup']],
                                   cwd=self.project, env={**self.env, 'CONDUCTOR_IS_LOCAL': host,
                                                         'CONDUCTOR_WORKSPACE_PATH': str(self.project)})
            self.assertEqual(json.loads(run.stdout)['setup']['host'], 'local' if host == '1' else 'cloud')
            if host == '1':
                self.assertEqual(snapshot(self.project), before)
                self.assertEqual(snapshot(self.home), home)
        self.assertEqual(marker.read_text(), 'kept\nkept\n')

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_upgrade_setup_preview_is_read_only_and_preserves_multiline_settings(self):
        import tomllib
        self.adopt()
        settings = self.project / '.conductor/settings.toml'
        settings.parent.mkdir()
        original = '# Owned\n[scripts]\nsetup = \'\'\'export FROM_PRIOR=yes\nprintf "prior\\n"\n\'\'\' # Retain setup context\narchive = "keep archive"\n[scripts.run.dev]\ncommand = "keep dev"\n'
        settings.write_text(original)
        command = [sys.executable, '-B', str(self.source / 'v0.5/scripts/upgrade-project.py'),
                   str(self.project), '--adopt-skills', '--conductor-setup']
        before, home = snapshot(self.project), snapshot(self.home)
        preview = self.run_command([*command, '--plan'])
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), home)
        plan = json.loads(next(line.split(': ', 1)[1] for line in preview.stdout.splitlines()
                               if line.startswith('Skill inventory adoption: ')))
        self.assertIn('conductor_setup', plan)
        self.assertTrue(plan['conductor_setup']['setup_after'].startswith('export FROM_PRIOR=yes\n'))
        self.run_command([*command, '--apply-safe', '--inventory-revision', plan['inventory_revision']])
        parsed = tomllib.loads(settings.read_text())
        self.assertTrue(parsed['scripts']['setup'].startswith('export FROM_PRIOR=yes\nprintf "prior\\n"\n'))
        self.assertEqual(parsed['scripts']['archive'], 'keep archive')
        self.assertEqual(parsed['scripts']['run']['dev']['command'], 'keep dev')
        self.assertIn('# Owned', settings.read_text())
        self.assertIn('# Retain setup context', settings.read_text())
        before = snapshot(self.project)
        self.adopt('--conductor-setup')
        self.assertEqual(snapshot(self.project), before)

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_composed_setup_preserves_prior_failure_and_reports_missing_toolchain(self):
        import tomllib
        settings = self.project / '.conductor/settings.toml'
        settings.parent.mkdir()
        settings.write_text('[scripts]\nsetup = "false"\n')
        self.adopt('--conductor-setup')
        command = tomllib.loads(settings.read_text())['scripts']['setup']
        before = snapshot(self.project)
        failed = self.run_command([shutil.which('sh'), '-c', command], cwd=self.project,
                         env={**self.env, 'CONDUCTOR_IS_LOCAL': '0',
                              'CONDUCTOR_WORKSPACE_PATH': str(self.project)}, code=1)
        self.assertIn('Prior project setup failed', failed.stderr)
        self.assertEqual(snapshot(self.project), before)
        hook = self.project / '.playbook/conductor-setup.sh'
        empty = self.root / 'empty-path'; empty.mkdir()
        run = self.run_command([shutil.which('sh'), str(hook)], cwd=self.project,
                               env={**self.env, 'PATH': str(empty), 'CONDUCTOR_IS_LOCAL': '0'}, code=2)
        self.assertIn('Python 3.10+', run.stderr)
        self.assertNotIn('Traceback', run.stderr)
        self.assertEqual(snapshot(self.project), before)

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_setup_preview_refuses_legacy_linked_or_customized_inputs_without_writes(self):
        self.adopt('--conductor-setup')
        settings = self.project / '.conductor/settings.toml'
        script = self.project / '.playbook/conductor-setup.sh'
        original_settings, original_script = settings.read_bytes(), script.read_bytes()
        command = [sys.executable, '-B', str(self.source / 'v0.5/scripts/upgrade-project.py'),
                   str(self.project), '--adopt-skills', '--conductor-setup', '--plan']
        for case in ('legacy', 'legacy-shared', 'linked', 'script', 'exit', 'suffix'):
            with self.subTest(case=case):
                settings.write_bytes(original_settings)
                script.write_bytes(original_script)
                legacy = self.project / ('.conductor/settings.json' if case == 'legacy-shared' else 'conductor.json')
                if case in ('legacy', 'legacy-shared'):
                    legacy.write_text('{"scripts":{"setup":"keep"}}')
                elif case == 'linked':
                    target = self.root / 'owned-settings.toml'
                    target.write_bytes(original_settings)
                    settings.unlink(); settings.symlink_to(target)
                elif case == 'script':
                    script.write_bytes(original_script + b'\n# user customization\n')
                elif case == 'exit':
                    settings.write_text('[scripts]\nsetup = "exit 0"\n')
                else:
                    settings.write_text(settings.read_text().replace('sh .playbook/conductor-setup.sh', 'sh custom-hook.sh'))
                before, home = snapshot(self.project), snapshot(self.home)
                rejected = self.run_command(command, code=2)
                self.assertIn('preserve', rejected.stderr)
                self.assertEqual(snapshot(self.project), before)
                self.assertEqual(snapshot(self.home), home)
                if settings.is_symlink():
                    settings.unlink()
                if legacy.exists():
                    legacy.unlink()

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_failed_setup_apply_restores_hook_and_prior_adoption(self):
        self.adopt()
        settings = self.project / '.conductor/settings.toml'
        settings.parent.mkdir()
        settings.write_text('[scripts]\nsetup = "keep project setup"\n')
        settings.chmod(0o444)
        self.addCleanup(lambda: settings.chmod(0o644) if settings.exists() else None)
        launcher = self.project / '.playbook/provision.pyz'
        launcher_before = launcher.read_bytes()
        before = snapshot(settings.parent)
        state = self.project / '.playbook-state.yml'
        record = next(s for s in state.read_text().splitlines() if s.startswith('skill_provisioning:'))
        command = [sys.executable, '-B', str(self.source / 'v0.5/scripts/upgrade-project.py'),
                   str(self.project), '--adopt-skills', '--conductor-setup']
        preview = self.run_command([*command, '--plan'])
        plan = json.loads(next(line.split(': ', 1)[1] for line in preview.stdout.splitlines()
                               if line.startswith('Skill inventory adoption: ')))
        self.run_command([*command, '--apply-safe', '--inventory-revision', plan['inventory_revision']], code=2)
        self.assertEqual(snapshot(settings.parent), before)
        self.assertEqual(launcher.read_bytes(), launcher_before)
        self.assertIn(record, state.read_text())
        self.assertFalse((self.project / '.playbook/conductor-setup.sh').exists())

    def test_alias_parent_links_and_existing_dangling_or_wrong_links_are_preserved(self):
        self.adopt()
        self.setup_report('0')
        alias = self.project / '.claude/skills/tdd'
        external = self.root / 'external-alias'
        external.mkdir(); (external / 'owned.txt').write_text('Keep external content\n')
        for destination in (external, self.root / 'missing-alias-target'):
            alias.unlink(); alias.symlink_to(destination, target_is_directory=True)
            before, outside = snapshot(self.project), snapshot(external)
            self.setup_report('0', code=2)
            self.assertEqual(snapshot(self.project), before)
            self.assertEqual(snapshot(external), outside)
        skills = self.project / '.claude/skills'
        skills.rename(self.root / 'saved-aliases')
        skills.symlink_to(external, target_is_directory=True)
        before, outside = snapshot(self.project), snapshot(external)
        self.setup_report('0', code=2)
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(external), outside)

    def test_missing_source_dependency_reports_repair_without_traceback_or_mutation(self):
        (self.source / 'v0.5/scripts/provisioning_state.py').unlink()
        for args in (('add', '.'), ('commit', '-qm', 'Fixture with missing runtime dependency'),
                     ('tag', '-fa', 'v0.5.999', '-m', 'Missing dependency fixture')):
            self.run_command(['git', '-C', str(self.source), *args])
        self.adopt()
        before, home = snapshot(self.project), snapshot(self.home)
        refused = self.setup_report('0', code=2)
        self.assertIn('provisioner failed', refused['repair'])
        self.assertNotIn('Traceback', json.dumps(refused))
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), home)

    @unittest.skipIf(sys.version_info < (3, 11), 'shared settings inspection requires Python 3.11+')
    def test_shared_maintainer_settings_use_candidate_without_consumer_bootstrap(self):
        import tomllib
        settings = tomllib.loads((ROOT / '.conductor/settings.toml').read_text())
        self.assertEqual(settings['$schema'], 'https://conductor.build/schemas/settings.repo.schema.json')
        self.assertNotEqual(self.source, ROOT)
        for host in ('1', '0'):
            run = self.run_command([shutil.which('sh'), '-c', settings['scripts']['setup']],
                                   cwd=self.source, env={**self.env, 'CONDUCTOR_IS_LOCAL': host})
            self.assertEqual(json.loads(run.stdout)['source']['kind'], 'maintainer-candidate')
            self.assertFalse((self.source / '.playbook-state.yml').exists())
            self.assertFalse((self.source / '.playbook/provision.pyz').exists())

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_local_hook_names_missing_source_and_reuses_an_explicitly_recovered_exact_cache(self):
        self.adopt('--conductor-setup')
        recorded = str(self.source)
        remote = self.root / 'teammate remote; literal'
        self.source.rename(remote)
        env = {**self.env, 'GIT_CONFIG_KEY_0': 'url.' + remote.as_uri() + '.insteadOf'}
        hook = self.project / '.playbook/conductor-setup.sh'
        local = {**env, 'CONDUCTOR_IS_LOCAL': '1'}
        before, home = snapshot(self.project), snapshot(self.home)
        refused = json.loads(self.run_command([shutil.which('sh'), str(hook)], cwd=self.project,
                                              env=local, code=2).stdout)
        self.assertIn(recorded, refused['repair'])
        self.assertIn('--acquire', refused['repair'])
        self.assertEqual((snapshot(self.project), snapshot(self.home)), (before, home))
        # The printed repair is an explicit, separate recovery; setup itself never downloads.
        cache = self.home / '.cache/agentic-engineering-playbook/sources'
        self.run_command([sys.executable, '-B', str(self.project / '.playbook/provision.pyz'),
                          '--project', str(self.project), '--source', recorded, '--acquire',
                          '--cache-dir', str(cache), 'preview'], env=env)
        self.assertEqual(snapshot(self.project), before)
        home = snapshot(self.home)
        report = json.loads(self.run_command([shutil.which('sh'), str(hook)], cwd=self.project,
                                             env=local).stdout)
        self.assertEqual(report['source_resolution']['mode'], 'reused')
        self.assertTrue(report['source_resolution']['path'].startswith(str(cache.resolve())))
        self.assertEqual((snapshot(self.project), snapshot(self.home)), (before, home))

    def test_moved_recorded_source_falls_back_to_the_verified_exact_cache(self):
        self.adopt('--conductor-setup')
        hook = self.project / '.playbook/conductor-setup.sh'
        (self.source / 'later.md').write_text('Later development\n')
        for args in (('add', '.'), ('commit', '-qm', 'Move the recorded checkout')):
            self.run_command(['git', '-C', str(self.source), *args])
        local = {**self.env, 'CONDUCTOR_IS_LOCAL': '1'}
        before, home = snapshot(self.project), snapshot(self.home)
        refused = json.loads(self.run_command([shutil.which('sh'), str(hook)], cwd=self.project,
                                              env=local, code=2).stdout)
        self.assertIn('--acquire', refused['repair'])
        self.assertEqual((snapshot(self.project), snapshot(self.home)), (before, home))
        cloud = json.loads(self.run_command([shutil.which('sh'), str(hook)], cwd=self.project,
                                            env={**self.env, 'CONDUCTOR_IS_LOCAL': '0'}).stdout)
        self.assertTrue(cloud['complete'])
        self.assertEqual(cloud['source_resolution']['mode'], 'acquired')
        self.assertTrue((self.source / 'later.md').is_file())
        before, home = snapshot(self.project), snapshot(self.home)
        report = json.loads(self.run_command([shutil.which('sh'), str(hook)], cwd=self.project,
                                             env=local).stdout)
        self.assertEqual(report['source_resolution']['path'], cloud['source_resolution']['path'])
        self.assertEqual((snapshot(self.project), snapshot(self.home)), (before, home))

    def test_recovery_prunes_only_owned_dangling_aliases_and_wires_delivery(self):
        self.adopt()
        self.assertTrue((self.project / '.agents/skills/ai-playbook-deliver/SKILL.md').is_file())
        self.setup_report('0')
        self.assertEqual(os.readlink(self.project / '.claude/skills/ai-playbook-deliver'),
                         '../../.agents/skills/ai-playbook-deliver')
        user_link = self.project / '.claude/skills/user-owned'
        user_link.symlink_to('../../elsewhere/user-owned')
        self.run_command([sys.executable, '-B', str(self.project / '.playbook/provision.pyz'),
                          '--project', str(self.project), '--source', str(self.source), 'recover'])
        aliases = self.project / '.claude/skills'
        dangling = [p.name for p in aliases.iterdir() if p.is_symlink() and not p.exists()]
        self.assertEqual(dangling, ['user-owned'])
        self.assertEqual(os.readlink(user_link), '../../elsewhere/user-owned')
        self.assertTrue((aliases / 'ai-playbook-deliver').exists())
        self.setup_report('0')
        self.assertTrue((aliases / 'tdd/SKILL.md').is_file())

    def test_cloud_setup_withholds_only_conflicting_claude_aliases(self):
        self.adopt()
        legacy = self.project / '.claude/commands/tdd.md'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('Keep the project command\n')
        refused = self.setup_report('0', code=2)
        self.assertTrue(refused['installation_complete'])
        self.assertFalse(refused['complete'])
        self.assertIn('tdd', refused['repair'])
        rows = {a['path']: a['status'] for a in refused['discovery_aliases'] if a['runtime'] == 'claude'}
        self.assertEqual(rows.pop('.claude/skills/tdd'), 'conflict')
        self.assertTrue(rows and set(rows.values()) == {'linked'}, rows)
        self.assertTrue((self.project / '.claude/skills/grilling').is_symlink())
        self.assertFalse((self.project / '.claude/skills/tdd').exists())
        self.assertEqual(legacy.read_text(), 'Keep the project command\n')
        before = snapshot(self.project)
        self.assertEqual(self.setup_report('0', code=2)['changed'], [])
        self.assertEqual(snapshot(self.project), before)

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_adopt_only_upgrade_refreshes_pristine_hook_and_keeps_setup_reconcilable(self):
        self.adopt('--conductor-setup')
        hook = self.project / '.playbook/conductor-setup.sh'
        released = self.source / 'v0.5/scripts/conductor-setup.sh'
        released.write_bytes(released.read_bytes() + b'# Next reviewed release\n')
        for args in (('add', '.'), ('commit', '-qm', 'Next synthetic release'),
                     ('tag', '-a', 'v0.5.1000', '-m', 'Next synthetic release')):
            self.run_command(['git', '-C', str(self.source), *args])
        upgrade = [sys.executable, '-B', str(self.source / 'v0.5/scripts/upgrade-project.py'),
                   str(self.project), '--adopt-skills']
        for extra in ((), ('--conductor-setup',)):
            with self.subTest(extra=extra):
                plan = json.loads(next(line.split(': ', 1)[1] for line in
                                       self.run_command([*upgrade, *extra, '--plan']).stdout.splitlines()
                                       if line.startswith('Skill inventory adoption: ')))
                self.run_command([*upgrade, *extra, '--apply-safe', '--inventory-revision',
                                  plan['inventory_revision']])
                self.assertEqual(hook.read_bytes(), released.read_bytes())
        hook.write_bytes(hook.read_bytes() + b'# user customization\n')
        customized = snapshot(self.project)
        rejected = self.run_command([*upgrade, '--conductor-setup', '--plan'], code=2)
        self.assertIn('customized conductor-setup.sh', rejected.stderr)
        self.assertEqual(snapshot(self.project), customized)

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_composition_keeps_non_ascii_and_names_unscannable_or_undecodable_setup(self):
        import tomllib
        settings = self.project / '.conductor/settings.toml'
        settings.parent.mkdir()
        original = 'printf "%s\\n" "\U0001F680 ready"'
        settings.write_text('[scripts]\nsetup = ' + json.dumps(original, ensure_ascii=False) + '\n')
        self.adopt('--conductor-setup')
        self.assertTrue(tomllib.loads(settings.read_text())['scripts']['setup'].startswith(original + '\n'))
        command = [sys.executable, '-B', str(self.source / 'v0.5/scripts/upgrade-project.py'),
                   str(self.project), '--adopt-skills', '--conductor-setup', '--plan']
        heredoc = "[scripts]\nsetup = '''cat <<EOF\nO'Brien\nEOF\n'''\n"
        for case, content, expected in (('heredoc', heredoc, 'project helper'),
                                        ('encoding', b'[scripts]\nsetup = "caf\xe9"\n', 'UTF-8'),
                                        ('shared-json', None, '.conductor/settings.json')):
            with self.subTest(case=case):
                if case == 'shared-json':
                    (self.project / '.conductor/settings.json').write_text('{"scripts":{"setup":"keep"}}')
                elif isinstance(content, bytes):
                    settings.write_bytes(content)
                else:
                    settings.write_text(content)
                before = snapshot(self.project)
                rejected = self.run_command(command, code=2)
                self.assertIn(expected, rejected.stderr)
                self.assertNotIn('Traceback', rejected.stderr)
                self.assertEqual(snapshot(self.project), before)

    def test_consumer_action_without_source_gets_consumer_repair(self):
        self.adopt()
        report = json.loads(self.run_command(
            [sys.executable, '-B', str(self.project / '.playbook/provision.pyz'), '--project',
             str(self.project), 'retain', '--skill', 'tdd'], code=2).stdout)
        self.assertIn('--source', report['repair'])
        self.assertNotIn('candidate', report['repair'])

    @unittest.skipIf(sys.version_info < (3, 11), 'shared settings inspection requires Python 3.11+')
    def test_maintainer_cloud_setup_output_keeps_the_candidate_checkout_clean(self):
        import tomllib
        settings = tomllib.loads((ROOT / '.conductor/settings.toml').read_text())
        shutil.copy2(ROOT / '.gitignore', self.source / '.gitignore')
        for args in (('add', '.gitignore'), ('commit', '-qm', 'Root ignore rules')):
            self.run_command(['git', '-C', str(self.source), *args])
        cloud = {**self.env, 'CONDUCTOR_IS_LOCAL': '0'}
        for _ in range(2):
            run = self.run_command([shutil.which('sh'), '-c', settings['scripts']['setup']],
                                   cwd=self.source, env=cloud)
            self.assertFalse(json.loads(run.stdout)['source']['dirty'])
        self.assertTrue((self.source / '.claude/skills/tdd').is_symlink())
        status = self.run_command(['git', '-C', str(self.source), 'status', '--porcelain',
                                   '--untracked-files=all'])
        self.assertEqual(status.stdout, '')

    @unittest.skipIf(sys.version_info < (3, 11), 'setup configuration parsing requires Python 3.11+')
    def test_adopted_hook_local_refuses_missing_source_and_cloud_restores_exact_release(self):
        self.adopt('--conductor-setup')
        remote = self.root / 'offline source; literal'
        self.source.rename(remote)
        env = {**self.env, 'GIT_CONFIG_KEY_0': 'url.' + remote.as_uri() + '.insteadOf'}
        hook = self.project / '.playbook/conductor-setup.sh'
        before, home = snapshot(self.project), snapshot(self.home)
        local = self.run_command([shutil.which('sh'), str(hook)], cwd=self.project,
                                 env={**env, 'CONDUCTOR_IS_LOCAL': '1'}, code=2)
        self.assertIn('source is missing', local.stdout)
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), home)
        cloud = self.run_command([shutil.which('sh'), str(hook)], cwd=self.project,
                                 env={**env, 'CONDUCTOR_IS_LOCAL': '0'})
        report = json.loads(cloud.stdout)
        self.assertTrue(report['complete'])
        self.assertEqual(report['source_resolution']['mode'], 'acquired')
        self.assertTrue((self.project / '.claude/skills/tdd/tests.md').is_file())
        self.assertEqual((self.project / '.playbook-state.yml').read_bytes(), before['.playbook-state.yml'][0])

    def test_adopted_setup_composes_existing_work_and_dispatches_by_actual_host(self):
        self.adopt()
        state = self.project / '.playbook-state.yml'
        adopted = state.read_bytes()
        # A local source must survive the same setup command used by Cloud.
        local = self.home / '.agents/skills/tdd'
        bundle = self.source / 'v0.5/bundles/mattpocock-skills'
        shutil.copytree(bundle / 'tdd', local)
        shutil.copy2(bundle / 'LICENSE', local / 'LICENSE')
        before_home, before_project = snapshot(self.home), snapshot(self.project)
        previous_work = self.root / 'existing-setup.log'
        launcher = self.project / '.playbook/provision.pyz'
        command = [sys.executable, '-B', str(launcher), '--project', '.',
                   '--source', str(self.source), 'setup']
        # Keep the project's own setup in its original noninteractive shell.
        setup = ('printf "prior setup\\n" >> ' + shlex.quote(str(previous_work))
                 + ' && ' + shlex.join(command))
        shell = shutil.which('sh')
        if shell is None:
            self.skipTest('noninteractive POSIX shell unavailable')
        local_run = self.run_command([shell, '-c', setup], cwd=self.project,
                                     env={**self.env, 'CONDUCTOR_IS_LOCAL': '1'})
        local_report = json.loads(local_run.stdout)
        self.assertEqual(local_report['setup'], {'host': 'local', 'action': 'discover'})
        self.assertEqual(local_report['changed'], [])
        self.assertEqual(local_report['runtime_resolution'], 'unverified')
        tdd = next(s for s in local_report['local_sources'] if s['name'] == 'tdd')
        self.assertEqual(tdd['status'], 'exact')
        self.assertEqual(snapshot(self.project), before_project)
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual(previous_work.read_text(), 'prior setup\n')

        cloud_run = self.run_command([shell, '-c', setup], cwd=self.project,
                                     env={**self.env, 'CONDUCTOR_IS_LOCAL': '0'})
        cloud_report = json.loads(cloud_run.stdout)
        self.assertEqual(cloud_report['setup'], {'host': 'cloud', 'action': 'install'})
        self.assertTrue(cloud_report['complete'])
        self.assertEqual(len(cloud_report['skills']), 11)
        self.assertEqual(cloud_report['source']['kind'], 'verified-release')
        self.assertTrue(all(s['qualification'] == 'unverified' for s in cloud_report['skills']))
        self.assertTrue((self.project / '.agents/skills/tdd/tests.md').is_file())
        self.assertTrue((self.project / '.agents/skills/tdd/LICENSE').is_file())
        self.assertEqual(state.read_bytes(), adopted)
        self.assertEqual(snapshot(self.home), before_home)
        installed = snapshot(self.project)
        repeat = self.run_command([shell, '-c', setup], cwd=self.project,
                                  env={**self.env, 'CONDUCTOR_IS_LOCAL': '0'})
        self.assertEqual(json.loads(repeat.stdout)['changed'], [])
        self.assertEqual(snapshot(self.project), installed)
        self.assertEqual(previous_work.read_text(), 'prior setup\n' * 3)

    def check_shell(self, name):
        shell = shutil.which(name)
        if shell is None:
            self.skipTest(name + ' unavailable; portable dispatch is covered with sh')
        self.adopt()
        for host in ('1', '0'):
            run = self.run_command([shell, '-c', shlex.join(self.setup_command())],
                                   env={**self.env, 'CONDUCTOR_IS_LOCAL': host},
                                   cwd=self.project)
            self.assertEqual(json.loads(run.stdout)['setup']['host'],
                             'local' if host == '1' else 'cloud')

    def test_setup_in_available_noninteractive_bash(self):
        self.check_shell('bash')

    def test_setup_in_available_noninteractive_zsh(self):
        self.check_shell('zsh')

    def test_cloud_setup_links_whole_skill_directories_and_preserves_conflicting_aliases(self):
        self.adopt()
        installed = self.setup_report('0')
        alias = self.project / '.claude/skills/tdd'
        self.assertTrue(alias.is_symlink())
        self.assertEqual(os.readlink(alias), '../../.agents/skills/tdd')
        target = self.project / '.agents/skills/tdd'
        for name in ('SKILL.md', 'tests.md', 'mocking.md', 'LICENSE', 'agents/openai.yaml'):
            self.assertEqual((alias / name).read_bytes(), (target / name).read_bytes())
        self.assertEqual((self.project / '.claude/skills/grill-with-docs/../grilling/SKILL.md').read_bytes(),
                         (self.project / '.agents/skills/grilling/SKILL.md').read_bytes())
        self.assertTrue(any(a['runtime'] == 'codex' and a['status'] == 'canonical'
                            for a in installed['discovery_aliases']))
        before, home = snapshot(self.project), snapshot(self.home)
        self.assertEqual(self.setup_report('0')['changed'], [])
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), home)
        alias.unlink()
        alias.mkdir(); (alias / 'owned.txt').write_text('Keep unknown alias content\n')
        before = snapshot(self.project)
        refused = self.setup_report('0', code=2)
        self.assertTrue(refused['installation_complete'])
        self.assertFalse(refused['complete'])
        self.assertTrue(any(a['status'] == 'conflict' and a['path'] == '.claude/skills/tdd'
                            for a in refused['discovery_aliases']))
        self.assertEqual(snapshot(self.project), before)
        self.setup_report('1')
        self.assertEqual(snapshot(self.project), before)

    def test_explicit_maintainer_candidate_setup_never_creates_consumer_state(self):
        before_home = snapshot(self.home)
        before_source = snapshot(self.source)
        local = self.setup_report('1', project=self.source, candidate=True)
        self.assertEqual(local['source']['kind'], 'maintainer-candidate')
        self.assertEqual(local['changed'], [])
        self.assertEqual(snapshot(self.source), before_source)
        self.assertEqual(snapshot(self.home), before_home)

        # The flag must not turn a consumer into a candidate installation.
        self.adopt()
        before = snapshot(self.project)
        refused = self.setup_report('0', candidate=True, code=2)
        self.assertIn('maintainer', refused['repair'])
        self.assertEqual(snapshot(self.project), before)
        cloud = self.setup_report('0', project=self.source, candidate=True)
        self.assertTrue(cloud['complete'])
        self.assertEqual(cloud['source']['kind'], 'maintainer-candidate')
        self.assertIsNone(cloud['source']['release'])
        self.assertFalse((self.source / '.playbook-state.yml').exists())
        self.assertFalse((self.source / '.playbook/provision.pyz').exists())
        self.assertFalse((self.source / '.playbook-config.json').exists())
        self.assertTrue(all(s['qualification'] == 'unverified' for s in cloud['skills']))
        installed = snapshot(self.source)
        repeat = self.setup_report('0', project=self.source, candidate=True)
        self.assertEqual(repeat['changed'], [])
        self.assertEqual(snapshot(self.source), installed)
        self.assertEqual(snapshot(self.home), before_home)

    def test_setup_requires_the_adopted_inventory_and_exact_launcher_before_writes(self):
        self.adopt()
        state = self.project / '.playbook-state.yml'
        launcher = self.project / '.playbook/provision.pyz'
        original_state, original_launcher = state.read_text(), launcher.read_bytes()
        line = next(s for s in original_state.splitlines() if s.startswith('skill_provisioning:'))
        record = json.loads(line.split(': ', 1)[1])
        for case in ('absent', 'malformed', 'duplicate-record', 'duplicate-field',
                     'launcher-proof', 'bundle-proof', 'changed-launcher',
                     'changed-launcher-and-proof', 'linked-launcher'):
            with self.subTest(case=case):
                state.write_text(original_state)
                if launcher.is_symlink():
                    launcher.unlink()
                launcher.write_bytes(original_launcher)
                changed = dict(record)
                if case == 'absent':
                    state.write_text(original_state.replace(line + '\n', ''))
                elif case == 'malformed':
                    state.write_text(original_state.replace(line, 'skill_provisioning: []'))
                elif case == 'duplicate-record':
                    state.write_text(original_state + line + '\n')
                elif case == 'duplicate-field':
                    duplicate = line[:-1] + ', "local_policy": "discover"}'
                    state.write_text(original_state.replace(line, duplicate))
                elif case in ('launcher-proof', 'bundle-proof'):
                    changed['launcher_sha256' if case == 'launcher-proof' else 'bundle_sha256'] = '0' * 64
                    state.write_text(original_state.replace(line, 'skill_provisioning: ' + json.dumps(changed)))
                elif case in ('changed-launcher', 'changed-launcher-and-proof'):
                    launcher.write_bytes(original_launcher + b'\n# modified launcher\n')
                    if case == 'changed-launcher-and-proof':
                        changed['launcher_sha256'] = hashlib.sha256(launcher.read_bytes()).hexdigest()
                        state.write_text(original_state.replace(line, 'skill_provisioning: ' + json.dumps(changed)))
                else:
                    external = self.root / 'linked-launcher.pyz'
                    external.write_bytes(original_launcher)
                    launcher.unlink(); launcher.symlink_to(external)
                before, home = snapshot(self.project), snapshot(self.home)
                refused = self.setup_report('0', code=2)
                self.assertFalse(refused['complete'])
                self.assertEqual(refused['changed'], [])
                self.assertTrue(refused['repair'])
                self.assertEqual(snapshot(self.project), before)
                self.assertEqual(snapshot(self.home), home)

    def test_setup_refuses_missing_host_and_local_acquisition_without_changes(self):
        self.adopt()
        before, home = snapshot(self.project), snapshot(self.home)
        for host in (None, '', 'true', 'local', '2', ' 0'):
            with self.subTest(host=host):
                refused = self.setup_report(host, code=2)
                self.assertIn('CONDUCTOR_IS_LOCAL', refused['repair'])
                self.assertEqual(refused['changed'], [])
                self.assertEqual(snapshot(self.project), before)
                self.assertEqual(snapshot(self.home), home)
        cache = self.root / 'unused-cache'
        missing = self.root / 'absent-source'
        refused = self.setup_report('1', '--acquire', '--cache-dir', str(cache),
                                    '--repository', str(self.source), source=missing, code=2)
        self.assertIn('local discovery never acquires', refused['repair'])
        self.assertFalse(cache.exists())
        missing_source = self.setup_report('1', '--cache-dir', str(cache), source=missing, code=2)
        self.assertIn('source is missing', missing_source['repair'])
        self.assertFalse(cache.exists())
        self.assertEqual(snapshot(self.project), before)
        self.assertEqual(snapshot(self.home), home)

    def test_setup_cannot_be_combined_with_launcher_export_or_skill_selection(self):
        self.adopt()
        exported = self.root / 'must-not-exist.pyz'
        before, home = snapshot(self.project), snapshot(self.home)
        for host in ('1', '0'):
            for extra in (('--write-launcher', str(exported)), ('--skill', 'tdd')):
                with self.subTest(host=host, extra=extra):
                    refused = self.setup_report(host, *extra, code=2)
                    self.assertIn('setup', refused['repair'])
                    self.assertFalse(exported.exists())
                    self.assertEqual(snapshot(self.project), before)
                    self.assertEqual(snapshot(self.home), home)

    def test_cloud_setup_recovers_only_the_adopted_source_and_reuses_it_offline(self):
        self.adopt()
        state = self.project / '.playbook-state.yml'
        adopted = state.read_bytes()
        commit = self.run_command(['git', '-C', str(self.source), 'rev-parse', 'HEAD']).stdout.strip()
        # A later remote release is not an automatic setup upgrade.
        (self.source / 'future.txt').write_text('Later source, not adopted\n')
        for args in (('add', '.'), ('commit', '-qm', 'Later fixture source'),
                     ('tag', '-a', 'v0.5.1000', '-m', 'Later fixture release')):
            self.run_command(['git', '-C', str(self.source), *args])
        missing, cache = self.root / 'absent-source', self.root / 'exact-source-cache'
        home = snapshot(self.home)
        restored = self.setup_report('0', '--acquire', '--cache-dir', str(cache),
                                     '--repository', str(self.source), source=missing)
        self.assertTrue(restored['complete'])
        self.assertEqual(restored['source']['commit'], commit)
        self.assertEqual(restored['source_resolution']['mode'], 'acquired')
        self.assertFalse((Path(restored['source_resolution']['path']) / 'future.txt').exists())
        self.assertEqual(state.read_bytes(), adopted)
        project, cached = snapshot(self.project), snapshot(cache)
        offline = self.root / 'offline-repository'
        for host, acquire in (('0', ['--acquire']), ('1', [])):
            repeated = self.setup_report(host, *acquire, '--cache-dir', str(cache),
                                        '--repository', str(offline), source=missing)
            self.assertEqual(repeated['source_resolution']['mode'], 'reused')
            self.assertEqual(repeated['changed'], [])
            self.assertEqual(snapshot(self.project), project)
            self.assertEqual(snapshot(cache), cached)
            self.assertEqual(snapshot(self.home), home)

    def test_cloud_setup_source_failures_leave_adoption_and_customizations_repairable(self):
        self.adopt()
        (self.project / 'custom.md').write_text('Retain project ownership\n')
        state = self.project / '.playbook-state.yml'
        adopted = state.read_text()
        for case in ('missing-proof', 'wrong-commit', 'offline', 'moved-tag'):
            with self.subTest(case=case):
                state.write_text(adopted)
                if case == 'missing-proof':
                    state.write_text(re.sub(r'^playbook_release_commit:.*$',
                                           'playbook_release_commit: null', adopted, flags=re.M))
                elif case == 'wrong-commit':
                    state.write_text(re.sub(r'^playbook_release_commit:.*$',
                                           'playbook_release_commit: "' + '0' * 40 + '"', adopted, flags=re.M))
                elif case == 'moved-tag':
                    self.run_command(['git', '-C', str(self.source), 'tag', '-fa',
                                      'v0.5.999', '-m', 'Deliberately moved fixture tag'])
                before, home = snapshot(self.project), snapshot(self.home)
                cache = self.root / ('failed-cache-' + case)
                repository = self.root / 'offline' if case == 'offline' else self.source
                refused = self.setup_report('0', '--acquire', '--cache-dir', str(cache),
                                            '--repository', str(repository),
                                            source=self.root / 'absent-source', code=2)
                self.assertFalse(refused['complete'])
                self.assertEqual(refused['changed'], [])
                self.assertTrue(refused['repair'])
                self.assertFalse(refused['adoption_changed'])
                self.assertEqual(snapshot(self.project), before)
                self.assertEqual(snapshot(self.home), home)
                self.assertEqual(list(cache.iterdir()) if cache.exists() else [], [])

    def test_setup_preserves_retained_content_and_reports_conflicts_without_disabling_other_skills(self):
        self.adopt()
        self.setup_report('0')
        for args in (('init', '-q'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@users.noreply.github.com')):
            self.run_command(['git', '-C', str(self.project), *args])
        custom = self.project / '.agents/skills/tdd/tests.md'
        custom.write_bytes(custom.read_bytes() + b'\nRetained project guidance\n')
        for args in (('add', '.agents/skills'), ('commit', '-qm', 'Retain fixture customization')):
            self.run_command(['git', '-C', str(self.project), *args])
        retain = self.setup_command('--skill', 'tdd')[:-1] + ['retain']
        self.run_command(retain)
        before = custom.read_bytes()
        repeated = self.setup_report('0')
        row = next(s for s in repeated['skills'] if s['name'] == 'tdd')
        self.assertEqual(row['installation'], 'customized')
        self.assertEqual(row['qualification'], 'unverified')
        self.assertEqual(custom.read_bytes(), before)
        custom.write_bytes(before + b'\nLater unretained edit\n')
        project, home = snapshot(self.project), snapshot(self.home)
        refused = self.setup_report('0', code=2)
        self.assertFalse(refused['complete'])
        self.assertIn('retain', refused['repair'])
        self.assertEqual(next(s for s in refused['skills'] if s['name'] == 'tdd')['installation'], 'conflict')
        unaffected = next(s for s in refused['skills'] if s['name'] == 'code-review')
        self.assertEqual(unaffected['installation'], 'installed')
        self.assertFalse(unaffected['embedded_compatible'])
        self.assertTrue(unaffected['fallback'])
        self.assertEqual(snapshot(self.project), project)
        self.assertEqual(snapshot(self.home), home)
        local = self.setup_report('1')
        self.assertTrue(all(not r['launched'] for r in local['job_routes'].values()))
        self.assertEqual(snapshot(self.project), project)
        self.assertEqual(snapshot(self.home), home)



if __name__ == '__main__':
    unittest.main()
