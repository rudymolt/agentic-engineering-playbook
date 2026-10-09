"""Current skill admission at the public library and JSON save boundaries."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_personal_presets as fixtures
from playbook_config import Configuration, encoded
from skill_bindings import JobBindings


# Fixed fixture injector shared by the library and CLI; never executes a skill.
INJECT = '''
def inject(point):
    if not fault.exists():
        return
    settings = json.loads(fault.read_text())
    if point != settings['point']:
        return
    fault.unlink()
    store = Path(settings['store'])
    source = store / 'SKILL.md'
    proof = store / 'evidence/fixture-audit.json'
    if settings['drift'] == 'source':
        source.write_text('changed synthetic source; never executed\\n')
    elif settings['drift'] in ('proof', 'contract'):
        audit = json.loads(proof.read_text())
        if settings['drift'] == 'proof':
            audit['independent'] = False
        else:
            audit['outputs'] = ['unqualified output']
        proof.write_text(json.dumps(audit))
        if settings['drift'] == 'contract':
            approval = json.loads((store / 'approvals.json').read_text())
            approval['audits']['fixture-audit']['evidence_sha256'] = fingerprint(proof)
            (store / 'approvals.json').write_text(json.dumps(approval))
    elif settings['drift'] == 'approval':
        approval = json.loads((store / 'approvals.json').read_text())
        approval['audits']['fixture-audit']['revision'] = 'changed'
        (store / 'approvals.json').write_text(json.dumps(approval))
    elif settings['drift'] in ('resolution', 'catalog'):
        bindings = json.loads((store / 'bindings.json').read_text())
        if settings['drift'] == 'resolution':
            other = store / 'replacement.md'
            other.write_bytes(source.read_bytes())
            bindings['sources']['custom:fixture-spec']['source'] = str(other)
        else:
            audit = json.loads(proof.read_text())
            audit['source_id'] = audit['invocation'] = 'custom:another-spec'
            extra = store / 'evidence/another-audit.json'
            extra.write_text(json.dumps(audit))
            approval = json.loads((store / 'approvals.json').read_text())
            approved = dict(approval['audits']['fixture-audit'])
            approved['source_id'] = 'custom:another-spec'
            approved['evidence_sha256'] = fingerprint(extra)
            approval['audits']['another-audit'] = approved
            (store / 'approvals.json').write_text(json.dumps(approval))
            bindings['sources']['custom:another-spec'] = dict(source=str(source), audits={'specification': 'another-audit'})
        (store / 'bindings.json').write_text(json.dumps(bindings))
    if settings['concurrent']:
        for destination in settings['destinations']:
            Path(destination).write_bytes(b'concurrent bytes must survive\\n')
'''


class SkillPublicationTests(unittest.TestCase):
    setUp = fixtures.PersonalPresetTests.setUp
    discover = fixtures.PersonalPresetTests.discover
    reusable_skill_fixture = fixtures.PersonalPresetTests.reusable_skill_fixture
    draft = fixtures.PersonalPresetTests.draft

    def fixture(self, action, replace, paired):
        self.store, source, _, identity = self.reusable_skill_fixture()
        self.service = Configuration(self.projects[0], self.discover, lambda: '2026-10-01T12:00:00Z',
                                     preferences_dir=self.local,
                                     bindings=JobBindings(self.projects[0], custom_dir=self.store))
        models = self.draft(self.service)['after']
        models['escalated_repair']['reasoning'] = 'medium'
        self.service.path.write_bytes(encoded(dict(schema_version=1, adopted=True, models=models)))
        older = dict(schema_version=1, adopted=True, models=deepcopy(models),
                     skills=JobBindings(self.projects[0]).defaults())
        older['skills']['jobs']['specification'] = [dict(source_id='custom:missing-spec',
                                                       source_sha256='a' * 64, contract_sha256='b' * 64)]
        preferences = dict(schema_version=1, presentation='guided', billing='unknown', presets={'Older': older})
        if replace:
            if action == 'Save defaults':
                preferences['defaults'] = deepcopy(older)
            else:
                preferences['presets']['Qualified'] = deepcopy(older)
        self.local.mkdir()
        self.personal = self.local / 'preferences.json'
        self.personal.write_bytes(encoded(preferences))
        draft = self.service.reply(self.service.read(), 'Goal fixture project')
        draft = self.service.reply(self.service.reply(draft, 'Expert'), 'Billing api')
        editor = self.service.reply(draft, 'Edit skills specification')
        option = next(i + 1 for i, row in enumerate(editor['skill_options']) if row['binding']['source_id'] == identity)
        draft = self.service.reply(editor, 'Choose ' + str(option))
        draft = self.service.reply(draft, action)
        if paired:
            pending = deepcopy(draft['personal'])
            draft = self.service.reply(draft, 'Recommended')
            self.assertEqual(draft['personal'], pending)
            # A distinct, unrelated project edit must not be published on rejection.
            draft = self.service.reply(self.service.reply(draft, 'Edit Repair'), '1')
        self.fault = self.root / 'fault.json'
        namespace = dict(fault=self.fault, json=json, Path=Path,
                         fingerprint=fixtures.fingerprint)
        exec(INJECT, namespace)
        self.service.checkpoint = namespace['inject']
        self.service.preferences.checkpoint = namespace['inject']
        return draft, source, preferences

    def call(self, proposal, reply, cli):
        if not cli:
            return self.service.reply(proposal, reply)
        adapter = self.root / 'discovery.py'
        adapter.write_text("import json,sys\nr=json.load(sys.stdin)\njson.dump(dict(request_id=r['request_id'],"
                           "checked_at=r['started_at'],authority='host-reported-selection',revision='fixture-1',"
                           "routes=[dict(model_id='fixture-model',runner='codex',reasoning='high',"
                           "roles=['planning','implementation','verification','escalated_repair'])]),sys.stdout)\n")
        wrapper = ("import json,sys,runpy\nfrom pathlib import Path\n"
                   "sys.path.insert(0,str(Path(sys.argv[1]).parent))\n"
                   "from playbook_config import Configuration\nfrom skill_bindings import fingerprint\n"
                   "fault=Path(" + repr(str(self.fault)) + ")\n" + INJECT +
                   "original=Configuration.__init__\ndef initialize(self,*a,**kw):\n"
                   " original(self,*a,**kw)\n self.checkpoint=inject\n"
                   " if self.preferences is not None: self.preferences.checkpoint=inject\n"
                   "Configuration.__init__=initialize\nsys.argv=sys.argv[1:]\n"
                   "runpy.run_path(sys.argv[0],run_name='__main__')\n")
        command = [sys.executable, '-c', wrapper, str(Path(__file__).with_name('configure-playbook.py')),
                   '--project', str(self.projects[0]), '--preferences-dir', str(self.local),
                   '--custom-bindings-dir', str(self.store), '--discovery-command',
                   json.dumps([sys.executable, str(adapter)]), '--now', '2026-10-01T12:00:00Z', 'reply']
        result = subprocess.run(command, input=json.dumps(dict(proposal=proposal, reply=reply)),
                                capture_output=True, text=True)
        self.assertEqual(result.stderr, '')
        value = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2 if value['state'] in ('blocked', 'recovery_required') else 0)
        return value

    def case(self, cli, paired, action, replace, point, drift, concurrent=False, recover=False):
        draft, source, preferences = self.fixture(action, replace, paired)
        before = (self.service.path.read_bytes(), self.personal.read_bytes())
        self.fault.write_text(json.dumps(dict(point=point, drift=drift, store=str(self.store),
                                             concurrent=concurrent,
                                             destinations=[str(self.service.path), str(self.personal)] if paired
                                             else [str(self.personal)])))
        result = self.call(draft, 'Apply' if paired else 'Apply preference', cli)
        self.assertFalse(self.fault.exists(), 'checkpoint must be exercised')
        self.assertFalse(result.get('launched', False))
        if drift is None:
            self.assertEqual(result['state'], 'applied' if paired else 'proposal_ready', result)
            if paired:
                self.assertTrue(result['paired_completion']['validated'])
            saved = json.loads(self.personal.read_text())
            candidate = saved['defaults'] if action == 'Save defaults' else saved['presets']['Qualified']
            JobBindings(self.projects[0], custom_dir=self.store).resolve(candidate['skills'], 'specification')
            self.assertEqual(saved['presets']['Older'], preferences['presets']['Older'])
            return result['state'], None
        self.assertIn(result['state'], ('blocked', 'recovery_required'), result)
        self.assertFalse(result.get('paired_completion', {}).get('validated', False))
        self.assertNotIn('saved and validated', result['message'])
        self.assertEqual(result['retained_proposal'], draft)
        if point == 'before_replace':
            self.assertEqual((self.service.path.read_bytes(), self.personal.read_bytes()), before)
        elif concurrent:
            for path in ((self.service.path, self.personal) if paired else (self.personal,)):
                self.assertEqual(path.read_bytes(), b'concurrent bytes must survive\n')
        if result['state'] == 'recovery_required':
            self.assertIn('recovery', result['message'].lower())
            self.assertEqual(self.service.read()['state'], 'recovery_required')
            if paired:
                for store in (self.service, self.service.preferences):
                    self.assertTrue(store.pair.exists())
                    journal = json.loads(store.pair.read_text())
                    self.assertEqual((store.project / journal['previous']).read_bytes(),
                                     before[0 if store is self.service else 1])
                    self.assertTrue((store.project / journal['attempted']).exists())
            else:
                self.assertTrue(self.service.preferences.recovery.exists())
                self.assertTrue(self.service.preferences.lock.exists())
        if not paired:
            self.assertEqual(self.service.path.read_bytes(), before[0])
        for project, runtime in zip(self.projects, self.runtime):
            self.assertEqual((project / '.playbook-state.yml').read_bytes(), runtime)
        self.assertFalse((self.projects[1] / '.playbook-config.json').exists())
        if recover:
            # Pre-mutation paired failure retains journals. Reconcile only disposable
            # fixture evidence after verifying both original destinations survived.
            if paired:
                for store in (self.service, self.service.preferences):
                    journal = json.loads(store.pair.read_text())
                    for key in ('previous', 'attempted'):
                        (store.project / journal[key]).unlink()
                    store.pair.unlink()
            editor = self.call(result, 'Edit skills specification', cli)
            for key in ('after', 'personal', 'context'):
                self.assertEqual(editor[key], draft[key])
            manual = next(i + 1 for i, row in enumerate(editor['skill_options'])
                          if row['binding']['source_id'] == 'playbook:specification-manual')
            chosen = self.call(editor, 'Choose ' + str(manual), cli)
            pending = chosen if paired else self.call(chosen, 'Expert', cli)
            self.assertEqual(self.call(pending, 'Apply' if paired else 'Apply preference', cli)['state'], 'blocked')
            ready = self.call(chosen, action, cli)
            if paired:
                ready = self.call(ready, 'Recommended', cli)
                ready = self.call(self.call(ready, 'Edit Repair', cli), '1', cli)
            saved = self.call(ready, 'Apply' if paired else 'Apply preference', cli)
            self.assertEqual(saved['state'], 'applied' if paired else 'proposal_ready', saved)
            personal = json.loads(self.personal.read_text())
            candidate = personal['defaults'] if action == 'Save defaults' else personal['presets']['Qualified']
            self.assertEqual(candidate['skills']['jobs']['specification'][0]['source_id'], 'playbook:specification-manual')
            self.assertEqual(personal['presets']['Older'], preferences['presets']['Older'])
        return result['state'], saved['state'] if recover else None

    def matrix(self, cli, points, drifts, replacements=(False,), recovery=False, concurrent=False):
        if cli:
            point = next((value for value in points if value.startswith('paired_')), points[0])
            paired = point.startswith('paired_')
            drift = next((value for value in drifts if value is not None), None)
            sample = (paired, 'Save defaults', replacements[0], point, drift, concurrent, recovery)
            outcomes = []
            for sample_cli in (False, True):
                try:
                    outcomes.append(self.case(sample_cli, *sample))
                finally:
                    fixtures.shutil.rmtree(self.store)
                    fixtures.shutil.rmtree(self.local)
                    for path in self.projects[0].glob('.playbook-config*'):
                        path.rmdir() if path.is_dir() else path.unlink()
            self.assertEqual(*outcomes)
            return
        for paired in (False, True):
            for action in ('Save defaults', 'Save preset Qualified'):
                for replace in replacements:
                    for point in points:
                        if point.startswith('paired_') and not paired:
                            continue
                        for drift in drifts:
                            with self.subTest(cli=cli, paired=paired, action=action, replace=replace,
                                              point=point, drift=drift, concurrent=concurrent):
                                try:
                                    self.case(cli, paired, action, replace, point, drift, concurrent, recovery)
                                finally:
                                    fixtures.shutil.rmtree(self.store)
                                    fixtures.shutil.rmtree(self.local)
                                    for path in self.projects[0].glob('.playbook-config*'):
                                        path.rmdir() if path.is_dir() else path.unlink()

    def test_model_only_project_apply_keeps_unadopted_skills_inert(self):
        for cli in (False, True):
            with self.subTest(cli=cli):
                try:
                    self.fixture('Save defaults', False, False)
                    draft = self.service.reply(self.service.read(), 'Goal fixture project')
                    draft = self.service.reply(self.service.reply(draft, 'Edit Repair'), '1')
                    self.assertFalse(draft['skills_adopted'])
                    self.assertEqual(draft['edited_jobs'], [])
                    self.assertEqual(draft['personal']['before'], draft['personal']['after'])
                    self.fault.write_text(json.dumps(dict(point='before_replace', drift='source',
                                                         store=str(self.store), concurrent=False,
                                                         destinations=[])))
                    result = self.call(draft, 'Apply', cli)
                    self.assertFalse(self.fault.exists())
                    self.assertEqual(result['state'], 'applied', result)
                    saved = json.loads(self.service.path.read_text())
                    self.assertNotIn('skills', saved)
                    self.assertEqual(saved['models'], draft['after'])
                finally:
                    fixtures.shutil.rmtree(self.store)
                    fixtures.shutil.rmtree(self.local)
                    for path in self.projects[0].glob('.playbook-config*'):
                        path.rmdir() if path.is_dir() else path.unlink()

    def test_library_before_replace_admission_and_explicit_recovery(self):
        self.matrix(False, ('before_replace',), (None, 'source'), (False, True), recovery=True)

    def test_cli_before_replace_admission_and_explicit_recovery(self):
        self.matrix(True, ('before_replace',), (None, 'source'), (False, True), recovery=True)

    def test_library_write_window_proof_contract_approval_resolution_catalog(self):
        self.matrix(False, ('before_replace',), ('proof', 'contract', 'approval', 'resolution', 'catalog'))

    def test_cli_write_window_proof_contract_approval_resolution_catalog(self):
        self.matrix(True, ('before_replace',), ('proof', 'contract', 'approval', 'resolution', 'catalog'))

    def test_library_late_admission_and_truthful_completion(self):
        self.matrix(False, ('before_publish', 'committed', 'before_completion', 'completion_sealed', 'paired_first_written',
                            'paired_before_completion', 'paired_completion_sealed'), (None, 'source'))

    def test_cli_late_admission_and_truthful_completion(self):
        self.matrix(True, ('before_publish', 'committed', 'before_completion', 'completion_sealed', 'paired_first_written',
                           'paired_before_completion', 'paired_completion_sealed'), (None, 'source'))

    def test_library_late_drift_preserves_concurrent_destinations(self):
        self.matrix(False, ('committed', 'before_completion', 'completion_sealed', 'paired_before_completion',
                            'paired_completion_sealed'), ('source',), concurrent=True)

    def test_cli_late_drift_preserves_concurrent_destinations(self):
        self.matrix(True, ('committed', 'before_completion', 'completion_sealed', 'paired_before_completion',
                           'paired_completion_sealed'), ('source',), concurrent=True)


if __name__ == '__main__':
    unittest.main()
