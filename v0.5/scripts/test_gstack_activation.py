"""Host publication through the provisioner CLI and a disposable runtime fixture."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

import gstack_activation
import gstack_package
import test_gstack_runtime as runtime_tests


class ManagedInvocationTest(unittest.TestCase):
    def test_codex_generated_commands_use_pinned_launchers_even_with_ambient_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            support = root / 'support'
            (support / 'playbook-bin').mkdir(parents=True)
            helper = support / 'playbook-bin/gstack-test'
            helper.write_text('#!/bin/sh\necho managed\n')
            helper.chmod(0o755)
            ambient = root / 'ambient'
            (ambient / 'bin').mkdir(parents=True)
            (ambient / 'lib').mkdir()
            (ambient / 'bin/gstack-test').write_text('#!/bin/sh\necho ambient\n')
            (ambient / 'bin/gstack-test').chmod(0o755)
            discover = (
                '[ -d "${GSTACK_ROOT:-/-}/lib" ]&&[ -d "$GSTACK_ROOT/bin" ]||GSTACK_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)/.agents/skills/gstack\n'
                '[ -d "$GSTACK_ROOT/bin" ]||GSTACK_ROOT=${CODEX_HOME:-~/.codex}/skills/gstack\n'
                '[ -d "$GSTACK_ROOT/bin" ]||echo "gstack: no install found (tried $GSTACK_ROOT).">&2\n'
                '"$GSTACK_ROOT/bin/gstack-test"\n')
            per_command = (
                '[ -d "${GSTACK_ROOT:-/-}/bin" ]&&[ -d "$GSTACK_ROOT/lib" ]||{ _r=$(git rev-parse --show-toplevel 2>/dev/null)/.agents/skills/gstack;'
                '[ -d "$_r/bin" ]||_r=${CODEX_HOME:-~/.codex}/skills/gstack;[ -d "$_r/bin" ]||{ echo "missing">&2;exit 1;};GSTACK_ROOT=$_r;}\n'
                'GSTACK_BIN=$GSTACK_ROOT/bin\n"$GSTACK_BIN/gstack-test"\n')
            for snippet in (discover, per_command):
                adapted = gstack_activation.relocate(snippet, support, 'learn', {'gstack-test'})
                self.assertNotIn('CODEX_HOME', adapted)
                result = subprocess.run(['bash', '-eu', '-c', adapted], cwd=root,
                                        env={'PATH': '/usr/bin:/bin', 'GSTACK_ROOT': str(ambient)},
                                        capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.strip(), 'managed')
            text = ('Read ~/.claude/skills/gstack/learn/sections/preamble.md\n'
                    'source "$GSTACK_BIN/gstack-lock.sh"\nbun "$GSTACK_ROOT/bin/gstack-render.ts"\n')
            self.assertEqual(gstack_activation.relocate(text, support, 'learn', {'gstack-lock.sh', 'gstack-render.ts'}),
                             f'Read sections/preamble.md\nsource "{support}/bin/gstack-lock.sh"\n'
                             f'{support.parent}/bin/bun "{support}/bin/gstack-render.ts"\n')

    def test_shipped_scripts_use_packaged_bun_and_nested_docs_use_host_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            support = root / 'payload/build'
            bun = support.parent / 'bin/bun'
            bun.parent.mkdir(parents=True)
            bun.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            bun.chmod(0o755)
            for script in ('gstack-design-md.ts', 'gstack-version-bump'):
                command = f'bun --no-env-file --config=/dev/null run "$GSTACK_ROOT/bin/{script}" check DESIGN.md'
                adapted = gstack_activation.relocate(command, support, 'design-review', {script})
                result = subprocess.run(['/bin/sh', '-eu', '-c', adapted], env={'PATH': '/empty'},
                                        capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.splitlines(),
                                 ['--no-env-file', '--config=/dev/null', 'run', f'{support}/bin/{script}', 'check', 'DESIGN.md'])
            evaluation = """bun --no-env-file --config=/dev/null -e 'await import(process.argv[1])' "$GSTACK_ROOT/lib/module.ts" """
            self.assertTrue(gstack_activation.relocate(evaluation, support, 'review', {}).startswith(f'{bun} '))
            project_command = 'bun run scripts/own.ts && bun run test'
            self.assertEqual(gstack_activation.relocate(project_command, support, 'review', {}), project_command)
            for host, directory in (('claude', 'document-release'), ('agents', 'gstack-document-release')):
                prompt = f'Read `${{HOME}}/.{host}/skills/gstack/document-release/SKILL.md` and its sections.'
                adapted = gstack_activation.relocate(prompt, support, 'ship', {})
                self.assertIn(f'`.{host}/skills/{directory}/SKILL.md`', adapted)
                self.assertNotIn(str(support), adapted)

    def test_user_only_claude_metadata_and_static_fallback(self):
        data = b'---\nname: learn\ndescription: Fixture\n---\nRun the original workflow.\n'
        support = Path('/fixture')
        user = gstack_activation.adapt_skill(data, support, 'claude', 'learn', {}, True)
        self.assertIn(b'\ndisable-model-invocation: true\n', user.split(b'\n---\n', 1)[0] + b'\n')
        for host in ('claude', 'codex'):
            notice = gstack_activation.adapt_skill(data, support, host, 'cso', {}, False)
            self.assertIn(b'manual static-review procedure', notice)
            self.assertNotIn(b'Run the original workflow', notice)

    def test_review_installs_and_reads_verified_checklist_on_both_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp).resolve()
            build = target / 'payload/build'
            codex_root = build / '.agents/skills'
            (codex_root / 'gstack-review').mkdir(parents=True)
            (build / 'review').mkdir()
            (build / 'LICENSE').write_text('MIT License')
            head = '---\nname: review\ndescription: Review changes\n---\n'
            (build / 'review/SKILL.md').write_text(head + 'Read `~/.claude/skills/gstack/review/checklist.md`.\n')
            (codex_root / 'gstack-review/SKILL.md').write_text(head + 'Read `$GSTACK_ROOT/review/checklist.md`.\n')
            checklist = build / 'review/checklist.md'
            checklist.write_text("A timing flake: route it to /investigate's flake recipe (timing flakes)\n")
            row = {'invocation': 'model', 'claude': gstack_package.endpoint(build, 'review'),
                   'codex': gstack_package.endpoint(codex_root, 'gstack-review')}
            record = {'source_files': {}, 'package': 'gstack', 'commit': 'fixture', 'version': 'fixture',
                      'skills': {'review': row}}
            for host in ('claude', 'codex'):
                outputs, _ = gstack_activation.materials(record, target, host)
                files = outputs[row[host]['directory']]
                self.assertIn(b'Read `checklist.md` in this installed review skill directory.', files['SKILL.md'])
                self.assertIn(b'Playbook stage 11', files['checklist.md'])
                self.assertNotIn(b'/investigate', files['checklist.md'])
                provenance = json.loads(files['PLAYBOOK-PROVENANCE.json'])
                self.assertEqual(provenance['source_files']['checklist.md'], row['claude']['files']['checklist.md'])
            checklist.write_text('drift')
            with self.assertRaisesRegex(gstack_package.bundle.BundleError, 'pinned host source differs'):
                gstack_activation.materials(record, target, 'codex')


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

    def history_snapshot(self):
        root = self.project / '.playbook/gstack-history'
        # Make an unnecessary atomic replacement observable without a sleep or
        # an assumption about the filesystem's timestamp resolution.
        for path in (root, root / 'operation.json'):
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        return self.read_history_snapshot()

    def read_history_snapshot(self):
        root = self.project / '.playbook/gstack-history'
        return {str(p.relative_to(root)): (p.stat().st_mode, p.stat().st_mtime_ns,
                                           p.read_bytes() if p.is_file() else None)
                for p in (root, *root.rglob('*'))}

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
        history_before = self.history_snapshot()
        before = (self.project / '.agents/skills/gstack-review/SKILL.md').stat().st_mtime_ns
        self.assertEqual(self.activate()['changed'], [])
        self.assertEqual(self.read_history_snapshot(), history_before)
        self.assertEqual((self.project / '.agents/skills/gstack-review/SKILL.md').stat().st_mtime_ns, before)
        self.assertTrue(self.activate('check-gstack')['complete'])
        recovered = self.activate('recover-gstack')
        self.assertTrue(recovered['recovery_complete'])
        self.assertFalse((self.project / '.agents/skills/gstack-review').exists())
        self.assertFalse((self.project / '.claude/skills/review').exists())
        history_before = self.history_snapshot()
        self.assertTrue(self.activate('recover-gstack')['recovery_complete'])
        self.assertEqual(self.read_history_snapshot(), history_before)

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


    def test_retiring_managed_endpoint_previews_both_hosts_preserves_edits_and_recovers(self):
        self.runtime()
        old = self.activate()
        endpoints = {row['host']: Path(row['path']) for row in old['skills'] if row['name'] == 'review'}
        originals = {host: (path / 'SKILL.md').read_bytes() for host, path in endpoints.items()}
        # Retire an existing endpoint in the fixture's next adopted inventory.
        registry_path = self.edition / 'upstream-skills.json'
        original_pin = {path: path.read_bytes() for path in (registry_path, self.record)}
        registry = json.loads(original_pin[registry_path])
        registry['skills']['review']['status'] = 'removed'
        registry['skills']['review']['removed_in'] = 'next'
        registry_path.write_text(json.dumps(registry))
        record = json.loads(original_pin[self.record])
        del record['skills']['review']
        self.record.write_text(json.dumps(record))
        next_pin = {path: path.read_bytes() for path in original_pin}
        self.runtime()

        def retirements(report):
            return {row['host']: row['installation'] for row in report['skills']
                    if row.get('retiring') and row['name'] == 'review'}

        expected = dict.fromkeys(endpoints, 'retirement_pending')
        self.assertEqual(retirements(self.activate('preview-gstack')), expected)
        self.assertEqual(retirements(self.activate('check-gstack', code=2)), expected)
        for host, path in endpoints.items():
            skill = path / 'SKILL.md'
            skill.write_text('custom instructions')
            self.assertEqual(retirements(self.activate('preview-gstack')), {**expected, host: 'conflict'})
            blocked = self.activate(code=2)
            self.assertEqual(blocked['changed'], [])
            self.assertEqual(skill.read_text(), 'custom instructions')
            self.assertTrue(all(p.exists() for p in endpoints.values()))
            skill.write_bytes(originals[host])

        applied = self.activate()
        self.assertTrue(applied['complete'])
        self.assertEqual(retirements(applied), dict.fromkeys(endpoints, 'retired'))
        self.assertTrue(all(not p.exists() for p in endpoints.values()))
        self.assertTrue(self.activate('check-gstack')['complete'])
        self.assertEqual(self.activate()['changed'], [])
        for path, data in original_pin.items():
            path.write_bytes(data)
        recovered = self.activate('recover-gstack')
        self.assertTrue(recovered['recovery_complete'])
        self.assertEqual({host: (p / 'SKILL.md').read_bytes() for host, p in endpoints.items()}, originals)

        # A deliberately preserved copy stays outside discovery. Rollback to
        # the prior pin can repair its missing endpoint without touching it.
        preserved = self.root / 'custom-review'
        endpoints['claude'].rename(preserved)
        (preserved / 'SKILL.md').write_text('kept custom instructions')
        for path, data in next_pin.items():
            path.write_bytes(data)
        preview = self.activate('preview-gstack')
        self.assertEqual(retirements(preview), {**expected, 'claude': 'already_absent'})
        self.assertTrue(self.activate()['complete'])
        for path, data in original_pin.items():
            path.write_bytes(data)
        self.assertTrue(self.activate()['complete'])
        self.assertTrue(self.activate('check-gstack')['complete'])
        self.assertEqual((endpoints['claude'] / 'SKILL.md').read_bytes(), originals['claude'])
        self.assertEqual((preserved / 'SKILL.md').read_text(), 'kept custom instructions')


if __name__ == '__main__':
    unittest.main()
