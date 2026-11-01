"""Adopted CLI fault probes for local support relocation and recovery."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_conductor_setup as fixtures

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ConductorSetupTest();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.adopt()
    def run_local(self,action,hook=None,expected=0):
        source=self.f.source; project=self.f.project
        def git(*args):
            return self.f.run_command(['git','-C',str(source),*args]).stdout.strip()
        command=[sys.executable,'-B',str(source/'v0.5/scripts/provision-skills.py')]
        if hook:
            command=[sys.executable,'-B','-c','import sys,runpy;sys.path.insert(0,'+repr(str(source/'v0.5/scripts'))+');exec('+repr(hook)+');runpy.run_path('+repr(str(source/'v0.5/scripts/provision-skills.py'))+',run_name="__main__")']
        command+=['--project',str(project),'--source',str(source),'--release','v0.5.999','--tag-object',git('rev-parse','v0.5.999'),'--commit',git('rev-parse','HEAD'),action+'-local']
        result=subprocess.run(command,env=self.f.env,capture_output=True,text=True)
        self.assertEqual(result.returncode,expected,result.stdout+result.stderr)
        return json.loads(result.stdout) if result.stdout else None
    def relocate(self):
        old=self.f.source;new=self.f.root/'recovered'
        old.rename(new);self.f.source=new
        self.f.env['GIT_CONFIG_KEY_0']='url.'+new.as_uri()+'.insteadOf'
    def snapshot(self):
        project=self.f.project
        return {str(p.relative_to(project)):p.read_bytes() for root in (project/'.agents/skills',project/'.playbook-base') for p in root.rglob('*') if p.is_file()}|{'.playbook-state.yml':(project/'.playbook-state.yml').read_bytes()}
    def test_interrupted_relocation_retries_and_can_recover(self):
        before=self.snapshot();self.relocate()
        hook='''import local_skill_transaction as t,os
original=t.write_file
def stop(*a):
 original(*a);os._exit(73)
t.write_file=stop
'''
        self.run_local('install',hook,73)
        report=self.run_local('recover')
        self.assertTrue(report['recovery_complete'])
        self.assertEqual(self.snapshot(),before)
        self.run_local('install',hook,73)
        self.assertTrue(self.run_local('install')['complete'])
        self.assertEqual(self.run_local('install')['changed'],[])
    def test_concurrent_state_edit_is_preserved_and_reported(self):
        self.relocate()
        hook='''import local_skill_transaction as t
original=t.write_file
def edit(project,*a):
 original(project,*a)
 p=project/'.playbook-state.yml';p.write_bytes(p.read_bytes()+b'\\n# concurrent user choice\\n')
t.write_file=edit
'''
        result=self.run_local('install',hook,2)
        self.assertTrue(result['transaction_pending']);self.assertTrue(result['changed'])
        self.assertIn('concurrent user choice',(self.f.project/'.playbook-state.yml').read_text())
        self.run_local('recover',expected=2)
        self.assertIn('concurrent user choice',(self.f.project/'.playbook-state.yml').read_text())
    def test_support_symlink_and_added_file_are_preserved(self):
        path=self.f.project/'.agents/skills/model-router/references/chat-prompts.md'
        path.unlink();path.symlink_to('/missing-sentinel')
        self.run_local('install',expected=2)
        self.assertTrue(path.is_symlink())
        path.unlink()
        extra=path.parent/'personal-note';extra.write_text('keep')
        self.assertTrue(self.run_local('install')['complete'])
        self.assertEqual(extra.read_text(),'keep')

    def test_state_edit_after_preflight_is_not_overwritten(self):
        self.relocate()
        hook = '''import local_skill_transaction as t
original=t.preflight
injected=False
def race(project,record):
 global injected
 original(project,record)
 changes=record['changes']
 if not injected and '.playbook-state.yml' in changes and all(t.read_regular(project,p)==t.unpack(v['after']) for p,v in changes.items() if p!='.playbook-state.yml'):
  p=project/'.playbook-state.yml'
  p.write_bytes(p.read_bytes()+b'\\n# concurrent independent choice\\n')
  injected=True
t.preflight=race
'''
        result = self.run_local('install', hook, expected=2)
        self.assertFalse(result['complete'])
        self.assertTrue(result['transaction_pending'])
        self.assertIn('concurrent independent choice', (self.f.project/'.playbook-state.yml').read_text())

    def test_hardlinked_skill_is_preserved_and_blocks_relocation(self):
        path = self.f.project/'.agents/skills/model-router/SKILL.md'
        peer = self.f.root/'shared-skill.md'
        os.link(path, peer)
        before = path.read_bytes()
        self.relocate()
        result = self.run_local('install', expected=2)
        self.assertFalse(result['complete'])
        self.assertEqual(path.stat().st_ino, peer.stat().st_ino)
        self.assertEqual(path.read_bytes(), before)

    def test_different_clean_release_cannot_repair_adopted_skills(self):
        source = self.f.source
        before = self.snapshot()
        (source/'fixture-marker').write_text('different release')
        for args in [('add','.'), ('commit','-qm','Different fixture release'),
                     ('tag','-fa','v0.5.999','-m','Different fixture release')]:
            self.f.run_command(['git','-C',str(source),*args])
        result = self.run_local('install', expected=2)
        self.assertFalse(result['complete'])
        self.assertEqual(self.snapshot(), before)

    def test_delivery_lock_types_and_duplicate_keys_return_incomplete_json(self):
        path = self.f.project/'.agents/skills/ai-playbook-deliver/manifest-lock.yml'
        original = path.read_text()
        for value in ('[]', 'null', 'true', '"bad"', '1', '{',
                      original.replace('"pack_digest":', '"pack_digest": "ignored", "pack_digest":', 1)):
            with self.subTest(value=value[:40]):
                path.write_text(value)
                result = self.run_local('check', expected=2)
                self.assertFalse(result['complete'])
                self.assertEqual(path.read_text(), value)

    def test_unreadable_source_support_does_not_shrink_required_inventory(self):
        relative = '.agents/skills/model-router/references/chat-prompts.md'
        target = self.f.project/relative
        target.unlink()
        source = self.f.source/'v0.5/skills/model-router/references/chat-prompts.md'
        hook = f'''from pathlib import Path
original=Path.read_text
def read(path,*a,**kw):
 if path.resolve()==Path({str(source)!r}).resolve():raise PermissionError('unreadable source support')
 return original(path,*a,**kw)
Path.read_text=read
'''
        result = self.run_local('install', hook, expected=2)
        self.assertFalse(result['complete'])
        self.assertFalse(target.exists())

    def test_written_paths_remain_reported_after_final_read_failure(self):
        relative = '.agents/skills/model-router/references/chat-prompts.md'
        path = self.f.project/relative
        original = path.read_bytes(); path.unlink()
        hook = '''import local_skill_transaction as t
original_write=t.write_file
original_read=t.read_regular
written=set()
def write(project,relative,*a):
 original_write(project,relative,*a);written.add(relative)
def read(project,relative):
 if relative in written:raise OSError('post-write read failure')
 return original_read(project,relative)
t.write_file=write;t.read_regular=read
'''
        result = self.run_local('install', hook, expected=2)
        self.assertFalse(result['complete'])
        self.assertIn(relative, result['changed'])
        self.assertIn(relative, result['observation_errors'])
        self.assertEqual(path.read_bytes(), original)

    def test_atomic_publication_is_reported_when_displaced_read_fails(self):
        self.relocate()
        hook = '''import local_skill_transaction as t
original_move=t.atomic_move
original_read=t.read_regular
failed=set()
def move(src,dst,**kw):
 original_move(src,dst,**kw)
 failed.update((str(src),str(dst)))
def read(project,relative):
 if str(project/relative) in failed:raise OSError('post-publication read failure')
 return original_read(project,relative)
t.atomic_move=move;t.read_regular=read
'''
        result = self.run_local('install', hook, expected=2)
        journal = json.loads((self.f.project/'.playbook/local-skill-history/operation.json').read_text())
        first = sorted(journal['changes'], key=lambda p: (p == '.playbook-state.yml', p))[0]
        self.assertFalse(result['complete'])
        self.assertTrue(result['transaction_pending'])
        self.assertIn(first, result['changed'])
        self.assertIn(first, result['observation_errors'])

    def test_pending_operation_preserves_unknown_partial_staging(self):
        relative = '.agents/skills/model-router/references/chat-prompts.md'
        path = self.f.project/relative
        expected = path.read_bytes(); path.unlink()
        hook = '''import local_skill_transaction as t,os
def stop(*a,**kw):os._exit(73)
t.write_file=stop
'''
        self.run_local('install', hook, expected=73)
        stage = path.with_name('.playbook-write-' + path.name)
        for material in (b'', expected[:12]):
            with self.subTest(material=material):
                stage.write_bytes(material)
                result = self.run_local('install', expected=2)
                self.assertFalse(result['complete'])
                self.assertTrue(result['transaction_pending'])
                self.assertEqual(stage.read_bytes(), material)
                self.assertFalse(path.exists())

    def test_last_moment_state_edit_survives_publication(self):
        self.relocate()
        hook = '''import local_skill_transaction as t
original=getattr(t,'atomic_move',t.os.replace)
fired=False
def race(src,dst,**kwargs):
 global fired
 if str(dst).endswith('/.playbook-state.yml') and not fired:
  p=t.Path(dst);p.write_bytes(p.read_bytes()+b'\\n# concurrent publication choice\\n');fired=True
 return original(src,dst,**kwargs)
if hasattr(t,'atomic_move'):t.atomic_move=race
else:t.os.replace=race
'''
        result = self.run_local('install', hook, expected=2)
        self.assertFalse(result['complete'])
        self.assertTrue(result['transaction_pending'])
        self.assertIn('concurrent publication choice', (self.f.project/'.playbook-state.yml').read_text())

    def test_interruption_after_atomic_swap_replays_and_recovers(self):
        before = self.snapshot()
        self.relocate()
        hook = '''import local_skill_transaction as t,os
original=t.atomic_move
def stop(*a,**kw):
 original(*a,**kw);os._exit(73)
t.atomic_move=stop
'''
        self.run_local('install', hook, 73)
        self.assertTrue(self.run_local('recover')['recovery_complete'])
        self.assertEqual(self.snapshot(), before)
        self.run_local('install', hook, 73)
        self.assertTrue(self.run_local('install')['complete'])
        self.assertEqual(self.run_local('install')['changed'], [])

    def test_unknown_staging_file_is_not_adopted(self):
        relative = '.agents/skills/model-router/references/chat-prompts.md'
        path = self.f.project/relative
        expected = path.read_bytes(); path.unlink()
        stage = path.with_name('.playbook-write-' + path.name)
        stage.write_bytes(expected)
        result = self.run_local('install', expected=2)
        self.assertFalse(result['complete'])
        self.assertEqual(stage.read_bytes(), expected)
        self.assertFalse(path.exists())


if __name__=='__main__':unittest.main()
