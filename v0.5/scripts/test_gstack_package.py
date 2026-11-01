"""Package acceptance through the public generator CLI and disposable Git source.

The Bun process is an external-tool fixture. Actual pinned Bun/upstream generation
is qualified separately; these tests cover source proof and publication behavior.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent


class GstackPackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.edition = self.root / 'v0.5'
        self.edition.mkdir()
        self.upstream = self.root / 'upstream'
        self.upstream.mkdir()
        self.env = {**os.environ, 'HOME': str(self.root / 'home'),
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                    'PYTHONDONTWRITEBYTECODE': '1'}
        Path(self.env['HOME']).mkdir()
        # A small independent upstream fixture with the observed alias/exclusion.
        self.write('VERSION', '1.62.0.0\n')
        self.write('LICENSE', 'MIT License\nFixture notice\n')
        self.write('bun.lock', '{"lockfileVersion": 1}\n')
        self.write('package.json', '{"name":"gstack","version":"1.62.0.0"}\n')
        self.write('scripts/gen-skill-docs.ts', '// External tool fixture input\n')
        for directory, declared in [('review', 'review'), ('open-gstack-browser', 'open-gstack-browser'),
                                    ('gstack-upgrade', 'gstack-upgrade'), ('codex', 'codex'), ('careful', 'careful')]:
            self.write(f'{directory}/SKILL.md', f'---\nname: {declared}\ndescription: Fixture skill\n---\nRead supporting material.\n')
            self.write(f'{directory}/references/guide.md', 'Complete reference\n')
            if directory != 'codex':
                endpoint = directory if directory == 'gstack-upgrade' else 'gstack-' + directory
                self.write(f'fixture-generated/{endpoint}/SKILL.md', f'---\nname: {declared}\ndescription: Generated skill\n---\nGenerated body.\n')
                self.write(f'fixture-generated/{endpoint}/agents/openai.yaml', 'interface:\n  display_name: "Fixture"\n')
        (self.upstream / 'connect-chrome').symlink_to('open-gstack-browser', target_is_directory=True)
        helper = self.write('bin/helper', '#!/bin/sh\nprintf helper\n')
        helper.chmod(0o755)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@users.noreply.github.com')
        self.git('add', '.')
        self.git('commit', '-qm', 'Pinned source')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        registry = json.loads((SCRIPTS.parent / 'upstream-skills.json').read_text())
        registry['packages']['gstack']['pin']['commit'] = self.commit
        registry['skills'] = {k: v for k, v in registry['skills'].items()
                              if v['package'] == 'gstack' and k in {'review', 'connect-chrome', 'gstack-upgrade', 'codex', 'careful'}}
        (self.edition / 'upstream-skills.json').write_text(json.dumps(registry))
        self.bun = self.root / 'bun-fixture'
        self.bun.write_text('#!' + sys.executable + '\n' + '''import pathlib, shutil, sys
if sys.argv[1:] == ['--version']:
    print('1.4.4')
elif sys.argv[1:] == ['install', '--frozen-lockfile', '--ignore-scripts']:
    pathlib.Path('node_modules').mkdir(exist_ok=True)
    pathlib.Path('node_modules/frozen-install').write_text('installed')
elif sys.argv[1:] == ['run', 'scripts/gen-skill-docs.ts', '--host', 'codex']:
    shutil.copytree('fixture-generated', '.agents/skills', dirs_exist_ok=True)
elif sys.argv[1:] == ['run', '--no-install', 'scripts/gen-skill-docs.ts', '--host', 'codex']:
    assert pathlib.Path('node_modules/frozen-install').is_file()
    shutil.copytree('fixture-generated', '.agents/skills', dirs_exist_ok=True)
else:
    raise SystemExit(99)
''')
        self.bun.chmod(0o755)
        self.record = self.edition / 'bundles/gstack/integrity.json'

    def write(self, name, data):
        path = self.upstream / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.upstream), *args], text=True, env=self.env)

    def command(self, *args, code=0):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'generate-skill-bundle.py'),
                                 '--package', 'gstack', '--edition', str(self.edition),
                                 '--bun', str(self.bun), *args], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_records_complete_pinned_source_and_selected_host_outputs(self):
        self.command('--upstream', str(self.upstream))
        record = json.loads(self.record.read_text())
        self.assertEqual(record['commit'], self.commit)
        self.assertEqual(record['source_files']['bin/helper']['mode'], '100755')
        self.assertEqual(record['source_files']['connect-chrome']['link'], 'open-gstack-browser')
        self.assertIn('review/references/guide.md', record['source_files'])
        self.assertEqual(record['skills']['connect-chrome']['claude']['declared_name'], 'open-gstack-browser')
        self.assertEqual(record['skills']['connect-chrome']['codex']['directory'], 'gstack-open-gstack-browser')
        self.assertEqual(record['skills']['gstack-upgrade']['codex']['directory'], 'gstack-upgrade')
        self.assertEqual(record['skills']['codex']['codex']['status'], 'unsupported')
        self.assertEqual(record['skills']['careful']['codex']['enforcement'], 'unsupported')
        self.assertEqual(record['generator']['bun_version'], '1.4.4')
        self.assertEqual(record['dependency_lock_sha256'], hashlib.sha256((self.upstream / 'bun.lock').read_bytes()).hexdigest())
        self.command('--check')

    def test_check_verifies_archive_bytes_without_running_tools(self):
        self.command('--upstream', str(self.upstream))
        archive = self.root / 'source.tar'
        archive.write_bytes(subprocess.check_output(['git', '-C', str(self.upstream), 'archive', '--format=tar', self.commit]))
        self.bun.unlink()
        self.command('--check', '--archive', str(archive))
        archive.write_bytes(archive.read_bytes()[:-100] + b'changed')
        result = self.command('--check', '--archive', str(archive), code=2)
        self.assertIn('archive integrity', result.stdout)

    def test_check_refuses_damaged_source_inventory(self):
        self.command('--upstream', str(self.upstream))
        record = json.loads(self.record.read_text())
        record['source_files']['review/SKILL.md']['sha256'] = '0' * 64
        self.record.write_text(json.dumps(record))
        self.command('--check', code=2)

    def test_check_refuses_overlapping_generated_files(self):
        self.command('--upstream', str(self.upstream))
        record = json.loads(self.record.read_text())
        record['skills']['review']['codex']['files']['SKILL.md/child'] = {'sha256': '0' * 64, 'size': 0}
        self.record.write_text(json.dumps(record))
        result = self.command('--check', code=2)
        self.assertIn('overlapping host', result.stdout)

    def test_unsafe_source_link_is_rejected_before_generator_execution(self):
        (self.upstream / 'escape').symlink_to('../outside')
        self.git('add', 'escape')
        self.git('commit', '-qm', 'Unsafe source')
        registry_path = self.edition / 'upstream-skills.json'
        registry = json.loads(registry_path.read_text())
        registry['packages']['gstack']['pin']['commit'] = self.git('rev-parse', 'HEAD').strip()
        registry_path.write_text(json.dumps(registry))
        self.command('--upstream', str(self.upstream), code=2)
        self.assertFalse(self.record.exists())

    def test_compound_source_alias_is_refused_before_generation(self):
        # Lexical normalization of x/../outside is insufficient: x may itself
        # resolve to a shallower directory, changing the meaning of '..'.
        (self.upstream / 'dir').mkdir()
        (self.upstream / 'dir/up').symlink_to('../review')
        (self.upstream / 'escape').symlink_to('dir/up/../../outside')
        self.write('outside', 'In-tree decoy\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Compound source aliases')
        registry_path = self.edition / 'upstream-skills.json'
        registry = json.loads(registry_path.read_text())
        registry['packages']['gstack']['pin']['commit'] = self.git('rev-parse', 'HEAD').strip()
        registry_path.write_text(json.dumps(registry))
        result = self.command('--upstream', str(self.upstream), code=2)
        self.assertIn('source alias', result.stdout)
        self.assertFalse(self.record.exists())

    def test_wrong_bun_version_leaves_source_and_destination_untouched(self):
        self.bun.write_text(self.bun.read_text().replace("print('1.4.4')", "print('1.4.5')"))
        result = self.command('--upstream', str(self.upstream), code=2)
        self.assertIn('requires Bun 1.4.4', result.stdout)
        self.assertFalse(self.record.exists())
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_generation_requires_frozen_dependencies_and_disables_auto_install(self):
        self.bun.write_text(self.bun.read_text().replace(
            "elif sys.argv[1:] == ['run', 'scripts/gen-skill-docs.ts', '--host', 'codex']:",
            "elif sys.argv[1:] == ['run', 'scripts/gen-skill-docs.ts', '--host', 'codex']:\n    raise SystemExit('unlocked execution refused')"))
        self.command('--upstream', str(self.upstream))

    def test_failed_frozen_install_never_falls_back_or_publishes(self):
        self.bun.write_text(self.bun.read_text().replace(
            "    pathlib.Path('node_modules').mkdir(exist_ok=True)",
            "    raise SystemExit('frozen lock refused')"))
        self.command('--upstream', str(self.upstream), code=2)
        self.assertFalse(self.record.exists())

    def test_ambient_ancestor_dependencies_are_refused(self):
        ancestor = self.root / 'ambient'
        (ancestor / 'node_modules').mkdir(parents=True)
        self.env['TMPDIR'] = str(ancestor)
        result = self.command('--upstream', str(self.upstream), code=2)
        self.assertIn('ambient dependency ancestor', result.stdout)
        self.assertFalse(self.record.exists())

    def test_symlinked_temp_directory_cannot_hide_physical_ancestor_dependencies(self):
        physical = self.root / 'physical'
        (physical / 'node_modules').mkdir(parents=True)
        (physical / 'nested').mkdir()
        alias = self.root / 'tmp-alias'
        alias.symlink_to(physical / 'nested', target_is_directory=True)
        self.env['TMPDIR'] = str(alias)
        result = self.command('--upstream', str(self.upstream), code=2)
        self.assertIn('ambient dependency ancestor', result.stdout)
        self.assertFalse(self.record.exists())

    def test_generation_uses_commit_bytes_and_preserves_existing_record(self):
        self.write('review/SKILL.md', 'Local customization\n')
        before = self.git('status', '--porcelain')
        self.command('--upstream', str(self.upstream))
        original = self.record.read_bytes()
        self.assertEqual(self.git('status', '--porcelain'), before)
        self.command('--upstream', str(self.upstream), code=2)
        self.assertEqual(self.record.read_bytes(), original)

    def test_local_git_replacement_and_export_attributes_cannot_substitute_pinned_code(self):
        original = self.git('show', self.commit + ':review/SKILL.md').encode()
        self.write('review/SKILL.md', '---\nname: review\ndescription: substituted\n---\nSubstituted body\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Local replacement')
        replacement = self.git('rev-parse', 'HEAD').strip()
        self.git('replace', self.commit, replacement)
        (self.upstream / '.git/info/attributes').write_text('LICENSE export-ignore\n')
        self.command('--upstream', str(self.upstream))
        record = json.loads(self.record.read_text())
        self.assertEqual(record['source_files']['review/SKILL.md']['sha256'], hashlib.sha256(original).hexdigest())
        self.assertIn('LICENSE', record['source_files'])

    def test_linked_output_parent_cannot_redirect_package_publication(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.edition / 'bundles').symlink_to(outside, target_is_directory=True)
        self.command('--upstream', str(self.upstream), code=2)
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
