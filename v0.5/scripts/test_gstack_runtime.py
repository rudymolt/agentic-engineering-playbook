"""Runtime acceptance at the provisioner CLI; fake Bun is an external tool fixture.

Actual frozen Linux builds are qualified separately. No host is activated here.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import unittest
import zipfile

import test_gstack_package as package_tests

SCRIPTS = package_tests.SCRIPTS


class GstackRuntimeTest(unittest.TestCase):
    write = package_tests.GstackPackageTest.write
    git = package_tests.GstackPackageTest.git
    command = package_tests.GstackPackageTest.command

    def setUp(self):
        package_tests.GstackPackageTest.setUp(self)
        self.command('--upstream', str(self.upstream))
        self.archive = self.root / 'source.tar'
        self.archive.write_bytes(subprocess.check_output(
            ['git', '-C', str(self.upstream), 'archive', '--format=tar', self.commit]))
        self.project = self.root / 'consumer'
        self.project.mkdir()
        self.store = self.root.resolve() / 'runtime-store'
        # A complete candidate checkout containing the public CLI and package.
        shutil.copytree(SCRIPTS, self.edition / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, env=self.env)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@users.noreply.github.com',
                        'commit', '--allow-empty', '-qm', 'Candidate'], check=True, env=self.env)
        self.bun.write_text(self.bun.read_text().replace('else:\n    raise SystemExit(99)', '''elif sys.argv[1:3] == ['run', '--no-install'] and sys.argv[-1] == 'vendor:xterm':
    pathlib.Path('extension/lib').mkdir(parents=True, exist_ok=True)
    pathlib.Path('extension/lib/xterm.js').write_text('vendored')
elif sys.argv[1:3] == ['build', '--compile']:
    output = pathlib.Path(sys.argv[sys.argv.index('--outfile') + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('#!/bin/sh\\nexit 0\\n')
    output.chmod(0o755)
else:
    raise SystemExit(99)'''))
        self.bun.write_text(self.bun.read_text().replace("['install', '--frozen-lockfile', '--ignore-scripts']:",
                                                       "['install', '--frozen-lockfile', '--ignore-scripts', '--backend=copyfile']:"))
        self.bun_zip = self.root / 'bun.zip'
        self.pack_bun()

    def pack_bun(self):
        with zipfile.ZipFile(self.bun_zip, 'w') as archive:
            archive.writestr('bun-linux-aarch64/bun', self.bun.read_bytes())
        policy = {'schema_version': 1, 'bun_version': '1.4.4', 'artifacts': {
            'linux-arm64': {'url': 'https://github.com/oven-sh/bun/releases/download/bun-v1.4.4/bun-linux-aarch64.zip',
                            'sha256': hashlib.sha256(self.bun_zip.read_bytes()).hexdigest(),
                            'size': self.bun_zip.stat().st_size,
                            'member': 'bun-linux-aarch64/bun'}}}
        (self.edition / 'bundles/gstack/runtime.json').write_text(json.dumps(policy))

    def runtime_command(self, action, flags=(), native=False):
        cli = self.edition / 'scripts/provision-skills.py'
        # Model the Linux OS boundary while exercising the same public CLI on Mac.
        wrapper = ('import sys,platform,runpy; sys.path.insert(0,' + repr(str(cli.parent)) + '); platform.system=lambda:"Linux"; '
                   'platform.machine=lambda:"aarch64"; runpy.run_path(' + repr(str(cli)) + ',run_name="__main__")')
        command = [sys.executable, str(cli)] if native else [sys.executable, '-c', wrapper]
        return [*command, '--source', str(self.root), '--candidate',
                                 '--project', str(self.project), '--runtime-store', str(self.store),
                                 '--gstack-archive', str(self.archive), '--bun-archive', str(self.bun_zip),
                                 action, *flags]

    def runtime(self, action='prepare-runtime', *flags, code=0, native=False):
        result = subprocess.run(self.runtime_command(action, flags, native),
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_cold_build_and_complete_offline_warm_replay(self):
        before = self.runtime('preview-runtime')
        self.assertFalse(before['runtime']['complete'])
        self.assertFalse(self.store.exists())
        installed = self.runtime()
        self.assertTrue(installed['runtime']['complete'])
        self.assertFalse(installed['complete'])  # No activation or qualification.
        payload = Path(installed['runtime']['path']) / 'payload'
        self.assertEqual((payload / 'source/review/references/guide.md').read_text(), 'Complete reference\n')
        self.assertTrue((payload / 'build/browse/dist/browse').is_file())
        self.assertFalse((self.project / '.agents').exists())
        self.archive.unlink()
        self.bun_zip.unlink()
        receipt = (payload.parent / 'receipt.json').read_bytes()
        self.assertTrue(self.runtime('prepare-runtime', '--offline')['runtime']['complete'])
        self.assertTrue(self.runtime('check-runtime', '--offline')['runtime']['complete'])
        self.assertEqual((payload.parent / 'receipt.json').read_bytes(), receipt)

    def test_helper_launcher_binds_packaged_bun_ahead_of_ambient_path(self):
        target = Path(self.runtime()['runtime']['path'])
        build = target / 'payload/build'
        # The fixture helper prints which interpreter its inherited PATH resolves.
        # Substitution here is isolated test input, never an activated receipt.
        (build / 'bin/helper').write_text('#!/bin/sh\ncommand -v bun\n')
        ambient = self.root / 'ambient'
        ambient.mkdir()
        fake = ambient / 'bun'
        fake.write_text('#!/bin/sh\necho AMBIENT\n')
        fake.chmod(0o755)
        launched = subprocess.run([str(build / 'playbook-bin/helper')],
                                  env={**self.env, 'PATH': str(ambient) + ':/usr/bin:/bin'},
                                  capture_output=True, text=True)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual(Path(launched.stdout.strip()).resolve(), target / 'payload/bin/bun')

    def test_missing_support_rebuilds_but_changed_or_extra_content_is_preserved(self):
        installed = self.runtime()
        target = Path(installed['runtime']['path'])
        support = target / 'payload/build/node_modules/frozen-install'
        support.unlink()
        self.assertFalse(self.runtime('check-runtime', code=2)['runtime']['complete'])
        self.assertTrue(self.runtime()['runtime']['complete'])
        self.assertTrue(list(self.store.glob('.gstack-previous-*')))
        support.write_text('customization')
        self.assertIn('changed', self.runtime(code=2)['error'])
        self.assertEqual(support.read_text(), 'customization')
        support.write_text('installed')
        (target / 'payload/build/unknown.txt').write_text('preserve')
        self.assertIn('unknown', self.runtime(code=2)['error'])
        self.assertEqual((target / 'payload/build/unknown.txt').read_text(), 'preserve')

    def test_failed_frozen_build_never_publishes_and_retry_succeeds(self):
        original = self.bun.read_text()
        self.bun.write_text(original.replace("    pathlib.Path('node_modules').mkdir(exist_ok=True)",
                                            "    raise SystemExit(74)"))
        self.pack_bun()
        self.assertIn('exit 74', self.runtime(code=2)['error'])
        self.assertFalse(list(self.store.glob('gstack-*')))
        self.bun.write_text(original)
        self.pack_bun()
        self.assertTrue(self.runtime()['runtime']['complete'])

    def test_damaged_archives_fail_before_executing_or_publishing(self):
        original = self.archive.read_bytes()
        self.archive.write_bytes(original + b'damaged')
        self.assertIn('integrity mismatch', self.runtime(code=2)['error'])
        self.archive.write_bytes(original)
        self.bun_zip.write_bytes(self.bun_zip.read_bytes() + b'damaged')
        self.assertIn('Bun artifact integrity mismatch', self.runtime(code=2)['error'])
        self.assertFalse(list(self.store.glob('gstack-*')))

    def test_offline_cold_build_fails_and_ignored_interrupted_stage_is_preserved(self):
        self.assertIn('offline runtime is incomplete', self.runtime('prepare-runtime', '--offline', code=2)['error'])
        stage = self.store / '.gstack-staging-interrupted'
        stage.mkdir()
        (stage / 'later-edit').write_text('preserve')
        self.assertTrue(self.runtime()['runtime']['complete'])
        self.assertEqual((stage / 'later-edit').read_text(), 'preserve')

    def test_offline_requires_saved_release_proof_before_public_lookup(self):
        command = self.runtime_command('check-runtime', ['--offline'])
        command.remove('--candidate')
        result = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('offline requires recorded release proof', json.loads(result.stdout)['error'])

    def test_malformed_receipt_is_a_json_error_and_preserved(self):
        target = Path(self.runtime()['runtime']['path'])
        receipt = target / 'receipt.json'
        receipt.write_text('null')
        self.assertIn('receipt identity', self.runtime('check-runtime', code=2)['error'])
        self.assertEqual(receipt.read_text(), 'null')

    def test_payload_root_mode_change_is_a_preserved_conflict(self):
        target = Path(self.runtime()['runtime']['path'])
        payload = target / 'payload'
        payload.chmod(0o777)
        self.assertIn('payload mode', self.runtime('check-runtime', code=2)['error'])
        self.assertEqual(payload.stat().st_mode & 0o777, 0o777)

    def test_store_in_project_or_behind_link_is_refused(self):
        self.store = self.project.resolve() / '.playbook/runtime'
        self.assertIn('separate', self.runtime(code=2)['error'])
        real = self.root.resolve() / 'real'
        real.mkdir()
        self.store = self.root.resolve() / 'alias'
        self.store.symlink_to(real, target_is_directory=True)
        self.assertIn('linked', self.runtime(code=2)['error'])
        self.assertEqual(list(real.iterdir()), [])

    def test_receipt_cannot_replace_inventory_with_a_completion_sentinel(self):
        installed = self.runtime()
        target = Path(installed['runtime']['path'])
        shutil.rmtree(target / 'payload')
        (target / 'payload').mkdir(mode=0o700)
        (target / 'payload/ready').write_text('ready')
        receipt = json.loads((target / 'receipt.json').read_text())
        receipt['files'] = {'ready': {'sha256': hashlib.sha256(b'ready').hexdigest(), 'size': 5, 'mode': 0o644}}
        (target / 'receipt.json').write_text(json.dumps(receipt))
        self.assertIn('inventory', self.runtime('check-runtime', code=2)['error'])

    def test_receipt_cannot_bless_changed_bun_or_omit_pinned_build_source(self):
        target = Path(self.runtime()['runtime']['path'])
        receipt_path = target / 'receipt.json'
        original_receipt = receipt_path.read_text()
        executable = target / 'payload/bin/bun'
        original_bun = executable.read_bytes()
        executable.write_bytes(b'#!/bin/sh\nexit 0\n')
        receipt = json.loads(original_receipt)
        receipt['files']['bin/bun'].update(sha256=hashlib.sha256(executable.read_bytes()).hexdigest(), size=executable.stat().st_size)
        receipt_path.write_text(json.dumps(receipt))
        self.assertIn('pinned', self.runtime('check-runtime', code=2)['error'])
        executable.write_bytes(original_bun)
        receipt = json.loads(original_receipt)
        (target / 'payload/build/bin/helper').unlink()
        del receipt['files']['build/bin/helper']
        receipt_path.write_text(json.dumps(receipt))
        self.assertIn('pinned', self.runtime('check-runtime', code=2)['error'])

    def test_termination_stops_the_active_build_process(self):
        heartbeat = self.root / 'heartbeat'
        process_id = self.root / 'child.pid'
        self.bun.write_text(self.bun.read_text().replace(
            "    pathlib.Path('node_modules').mkdir(exist_ok=True)",
            f"    import os,time\n    pathlib.Path({str(process_id)!r}).write_text(str(os.getpid()))\n"
            f"    while True:\n        pathlib.Path({str(heartbeat)!r}).write_text(str(time.monotonic()))\n        time.sleep(0.05)"))
        self.pack_bun()
        process = subprocess.Popen(self.runtime_command('prepare-runtime'), env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not heartbeat.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(heartbeat.exists())
            process.terminate()
            stdout, stderr = process.communicate(timeout=10)
            before = heartbeat.read_text()
            time.sleep(0.3)
            self.assertEqual(heartbeat.read_text(), before, 'build process kept writing after termination')
            self.assertEqual(process.returncode, 2, stdout + stderr)
            self.assertFalse(json.loads(stdout)['complete'])
            self.assertFalse(list(self.store.glob('gstack-*')))
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            if process_id.exists():
                try:
                    os.kill(int(process_id.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    unittest.main()
