"""Delayed public advice projections retain dates without extending claim life."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_model_recommendations as fixtures
from playbook_config import Configuration


class AdviceProjectionTests(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover

    def conversation(self, surface, kind, keep_source=False):
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        root = Path(private.name)
        cache, personal = root / 'cache', root / 'personal'
        personal.mkdir()
        (personal / 'preferences.json').write_text('{"schema_version":1,"presentation":"expert"}\n')
        now = ['2026-10-02T11:59:59Z']
        evidence = deepcopy(self.evidence)
        evidence['rates'][0]['output'] = 8
        for claims in (evidence['guidance'], evidence['rates']):
            for claim in claims:
                claim['checked_at'] = '2026-10-02T11:59:59Z'
        if kind:
            evidence[kind][0]['checked_at'] = fixtures.NOW
        # Younger envelope and sibling must not extend the selected claim.
        evidence['guidance'].append({**evidence['guidance'][0], 'model_id': 'unselected-sibling',
                                     'checked_at': now[0]})
        evidence['guidance'].append({**evidence['guidance'][0], 'text': 'Younger sibling guidance',
                                     'checked_at': now[0]})
        evidence['rates'].append({**evidence['rates'][0], 'model_id': 'unselected-sibling',
                                 'checked_at': now[0]})
        evidence['sources'] = [dict(source_url=url, checked_at=now[0], status='retrieved')
                               for url in (fixtures.GUIDANCE, fixtures.PRICING)]
        self.context['workload'] = dict(input_tokens=1000000, output_tokens=1000000, retries=1,
                                       billing_route='standard-short-context-uncached')
        fetches = []
        if surface == 'library':
            def source():
                fetches.append(1)
                return deepcopy(evidence)
            service = Configuration(self.project, self.discover, lambda: now[0], context=self.context,
                                    recommendation_sources=source, evidence_dir=cache, preferences_dir=personal)
            def invoke(proposal=None, reply=None):
                return service.read() if proposal is None else service.reply(proposal, reply)
        else:
            source = root / 'source.json'
            source.write_text(json.dumps(evidence))
            adapter = "import json,sys; r=json.load(sys.stdin); json.dump(dict(request_id=r['request_id'],checked_at=r['started_at'],authority='host-reported-selection',revision='fixture',routes=" + repr(self.routes) + "),sys.stdout)"
            wrapper = root / 'cli.py'
            wrapper.write_text("import runpy,sys,urllib.request\nfrom pathlib import Path\n"
                               "def forbidden(*args,**kwargs): raise AssertionError('Unexpected official GET')\n"
                               "urllib.request.OpenerDirector.open=forbidden\n"
                               "sys.path.insert(0,str(Path(sys.argv[1]).parent))\n"
                               "runpy.run_path(sys.argv.pop(1),run_name='__main__')\n")
            def invoke(proposal=None, reply=None):
                command = [sys.executable, str(wrapper), str(Path(__file__).with_name('configure-playbook.py')),
                           '--project', str(self.project), '--now', now[0], '--evidence-dir', str(cache),
                           '--preferences-dir', str(personal), '--evidence-fixture', str(source),
                           '--discovery-command', json.dumps([sys.executable, '-c', adapter]),
                           'read' if proposal is None else 'reply']
                request = {'context': self.context} if proposal is None else {'proposal': proposal, 'reply': reply}
                process = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
                result = json.loads(process.stdout)
                self.assertEqual(process.returncode, 2 if result['state'] in {'blocked', 'recovery_required'} else 0,
                                 process.stderr + process.stdout)
                self.assertEqual(process.stderr, '')
                return result
        original = invoke()
        if surface == 'cli' and not keep_source:
            source.unlink()
        before = {str(p): p.read_bytes() for folder in (self.project, cache, personal)
                  for p in folder.rglob('*') if p.is_file()}
        def unchanged():
            self.assertEqual({str(p): p.read_bytes() for folder in (self.project, cache, personal)
                              for p in folder.rglob('*') if p.is_file()}, before)
            if surface == 'library':
                self.assertEqual(fetches, [1])
        return invoke, now, original, unchanged

    def assert_advice(self, result, kind, usable):
        advice = result['recommendations']['implementation']
        if kind == 'guidance' and not usable:
            self.assertIsNone(advice['choice'])
            self.assertIsNone(advice['guidance'])
            self.assertIsNone(advice['cost'])
        else:
            self.assertEqual(advice['choice']['model_id'], 'fixture-code')
            self.assertIsNotNone(advice['guidance'])
            if kind == 'rates' and not usable:
                self.assertIsNone(advice['cost']['rates'])
                self.assertIsNone(advice['cost']['estimate'])
            else:
                self.assertEqual(advice['cost']['rates']['input'], 2)
                self.assertEqual(advice['cost']['estimate']['amount'], 20)
        if not usable:
            self.assertIn('Refresh', advice['limitations'])
            self.assertIn('stale', json.dumps(advice))
            self.assertEqual(advice['withheld_evidence'][kind]['checked_at'], fixtures.NOW)
            self.assertEqual(advice['withheld_evidence'][kind]['uncertainty'],
                             'Synthetic controlled evidence, not current rates.')
        if 'explanation' in result:
            self.assertEqual(result['explanation']['recommendation'], advice)
        self.assertEqual(next(row for row in result['role_proposal'] if row['role'] == 'implementation')['recommendation'], advice)
        if isinstance(result['recommended']['advice'], dict):
            self.assertEqual(result['recommended']['advice']['implementation'], advice)
        if 'replacement' in result and result['replacement']['role'] == 'implementation':
            self.assertEqual(result['replacement']['advice'], advice)

    def test_delayed_explain_library_and_cli_individual_boundaries(self):
        for surface in ('library', 'cli'):
            for kind in ('guidance', 'rates'):
                with self.subTest(surface=surface, kind=kind):
                    invoke, now, original, unchanged = self.conversation(surface, kind)
                    untouched = deepcopy(original)
                    for age in (86399, 86400, 86401):
                        now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00')) + timedelta(seconds=age)).isoformat()
                        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Unexpected GET')):
                            result = invoke(original, 'Explain Build')
                            self.assert_advice(result, kind, age <= 86400)
                            repeated = invoke(result, 'Explain Build')
                            self.assert_advice(repeated, kind, age <= 86400)
                        self.assertEqual(result['after'], original['after'])
                        self.assertEqual(result['before'], original['before'])
                        self.assertEqual(original, untouched)
                        unchanged()

    def test_display_only_reply_withholds_expired_original_claim(self):
        for surface in ('library', 'cli'):
            for kind in ('guidance', 'rates'):
                with self.subTest(surface=surface, kind=kind):
                    invoke, now, original, unchanged = self.conversation(surface, kind)
                    now[0] = '2026-10-02T12:00:01Z'
                    result = invoke(original, 'Presets')
                    self.assert_advice(result, kind, False)
                    self.assertEqual(result['after'], original['after'])
                    unchanged()

    def test_preview_and_rejected_accept_own_the_selected_claim(self):
        for surface in ('library', 'cli'):
            for kind in ('guidance', 'rates'):
                with self.subTest(surface=surface, kind=kind):
                    invoke, now, original, unchanged = self.conversation(surface, kind)
                    role = original['replacement']['role']
                    for age in (86399, 86400, 86401):
                        now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00'))
                                  + timedelta(seconds=age)).isoformat()
                        with self.subTest(age=age):
                            for reply in ('Back', 'Recommended', 'Save defaults', 'Expert'):
                                result = invoke(original, reply)
                                self.assert_advice(result, kind, age <= 86400)
                                self.assertEqual(result['after'], original['after'])
                            accepted = invoke(original, 'Accept replacement')
                            self.assert_advice(accepted, kind, age <= 86400)
                            if kind == 'guidance' and age > 86400:
                                self.assertEqual(accepted['after'], original['after'])
                                self.assertNotIn('Accept replacement', accepted['choices'])
                                repeated = invoke(accepted, 'Accept replacement')
                                self.assertEqual(repeated['after'], original['after'])
                                self.assert_advice(repeated, kind, False)
                            else:
                                self.assertEqual(accepted['after'][role]['model_id'], 'fixture-code')
                            unchanged()

    def test_malformed_advice_root_cannot_authorize_nested_recovery(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'guidance')
            for root in (None, {}, [], 'invalid', {'implementation': None}):
                for age in (86399, 86400, 86401):
                    now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00'))
                              + timedelta(seconds=age)).isoformat()
                    for reply in (['invalid typed reply'], 'unknown', 'Back', 'Explain Build', 'Accept replacement'):
                        with self.subTest(surface=surface, root=root, age=age, reply=reply):
                            draft = deepcopy(original)
                            draft['recommendations'] = root
                            draft['proposal_revision'] = Configuration._revision(draft)
                            result = invoke(draft, reply)
                            retained = result.get('retained_proposal', result)
                            self.assertEqual(retained['after'], original['after'])
                            self.assertNotIn('Accept replacement', retained.get('choices', []))
                            copies = [row['recommendation'] for row in retained.get('role_proposal', [])]
                            for owner, key in (('replacement', 'advice'), ('explanation', 'recommendation')):
                                if owner in retained:
                                    copies.append(retained[owner][key])
                            if isinstance(retained.get('recommended', {}).get('advice'), dict):
                                copies.extend(retained['recommended']['advice'].values())
                            self.assertTrue(copies)
                            for advice in copies:
                                self.assertIsNone(advice['choice'])
                                self.assertIsNone(advice['cost'])
                                self.assertIn('Refresh', advice['limitations'])
                            self.assertIn(fixtures.NOW, json.dumps(copies))
                            repeated = invoke(retained, 'Accept replacement')
                            self.assertEqual(repeated.get('retained_proposal', repeated)['after'], original['after'])
                            unchanged()

    def test_invalid_reply_retains_fresh_positive_advice(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'guidance')
            result = invoke(original, ['invalid typed reply'])
            self.assertEqual(result['state'], 'blocked')
            self.assert_advice(result['retained_proposal'], 'guidance', True)
            self.assertIn('Accept replacement', result['retained_proposal']['choices'])
            unchanged()

    def test_accept_requires_the_same_original_claim_in_both_copies(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'guidance')
            role = original['replacement']['role']
            for mutation in ('missing root claim', 'malformed root claim', 'different nested claim'):
                with self.subTest(surface=surface, mutation=mutation):
                    draft = deepcopy(original)
                    if mutation == 'different nested claim':
                        draft['replacement']['advice']['guidance']['checked_at'] = now[0]
                    else:
                        draft['recommendations'][role]['guidance'] = None if mutation == 'missing root claim' else []
                    draft['proposal_revision'] = Configuration._revision(draft)
                    rejected = invoke(draft, 'Accept replacement')
                    self.assertEqual(rejected['after'], original['after'])
                    self.assertNotIn('Accept replacement', rejected['choices'])
                    self.assertIn('Refresh', rejected['choices'])
                    repeated = invoke(rejected, 'Accept replacement')
                    self.assertEqual(repeated['after'], original['after'])
                    unchanged()

    def test_each_nested_copy_is_checked_without_a_root_or_role_label(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'guidance')
            now[0] = '2026-10-02T12:00:01Z'
            selected = deepcopy(original['recommendations']['implementation'])
            for owner in ('replacement', 'role_proposal', 'recommended', 'explanation'):
                with self.subTest(surface=surface, owner=owner):
                    draft = deepcopy(original)
                    draft.pop('recommendations')
                    for key in ('replacement', 'role_proposal', 'recommended', 'explanation'):
                        draft.pop(key, None)
                    # Labels are not evidence either: an orphan copy still needs projection.
                    draft[owner] = {'advice': selected} if owner == 'replacement' else (
                        [{'recommendation': selected}] if owner == 'role_proposal' else (
                            {'advice': {'implementation': selected}} if owner == 'recommended' else
                            {'recommendation': selected}))
                    draft['proposal_revision'] = Configuration._revision(draft)
                    result = invoke(draft, ['invalid typed reply'])['retained_proposal']
                    advice = (result[owner]['advice'] if owner == 'replacement' else
                              result[owner][0]['recommendation'] if owner == 'role_proposal' else
                              result[owner]['advice']['implementation'] if owner == 'recommended' else
                              result[owner]['recommendation'])
                    self.assertIsNone(advice['choice'])
                    self.assertIsNone(advice['cost'])
                    self.assertEqual(advice['withheld_evidence']['guidance']['checked_at'], fixtures.NOW)
                    self.assertIn('Refresh', advice['limitations'])
                    self.assertNotIn('Accept replacement', result['choices'])
                    unchanged()

    def test_inadequate_previous_success_and_missing_pricing(self):
        for surface in ('library', 'cli'):
            for kind in ('guidance', 'rates'):
                for date, status in ((fixtures.NOW, 'failed'), (fixtures.NOW, 'unrecognized'),
                                     ('future', None), (None, None), ('malformed', None)):
                    with self.subTest(surface=surface, kind=kind, date=date, status=status):
                        invoke, now, original, unchanged = self.conversation(surface, kind)
                        draft = deepcopy(original)
                        role_advice = draft['recommendations']['implementation']
                        claim = role_advice['guidance'] if kind == 'guidance' else role_advice['cost']['rates']
                        claim['checked_at'] = '2027-01-01T00:00:00Z' if date == 'future' else date
                        if status:
                            claim['status'] = status
                        draft['proposal_revision'] = Configuration._revision(draft)
                        result = invoke(draft, 'Explain Build')
                        advice = result['explanation']['recommendation']
                        if kind == 'guidance':
                            self.assertIsNone(advice['choice'])
                            self.assertIsNone(advice['cost'])
                        else:
                            self.assertIsNotNone(advice['choice'])
                            self.assertIsNone(advice['cost']['rates'])
                            self.assertIsNone(advice['cost']['estimate'])
                        self.assertIn('Refresh', advice['limitations'])
                        self.assertEqual(advice['withheld_evidence'][kind]['checked_at'], claim['checked_at'])
                        unchanged()
            invoke, now, original, unchanged = self.conversation(surface, None)
            draft = deepcopy(original)
            for advice in draft['recommendations'].values():
                advice['cost']['rates'] = None
            draft['proposal_revision'] = Configuration._revision(draft)
            result = invoke(draft, 'Explain Build')
            self.assertIsNotNone(result['explanation']['recommendation']['choice'])
            self.assertIsNone(result['explanation']['recommendation']['cost']['rates'])
            self.assertIsNone(result['explanation']['recommendation']['cost']['estimate'])
            unchanged()

    def test_recovery_display_and_back_recheck_stored_advice(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'guidance')
            now[0] = '2026-10-02T12:00:01Z'
            with self.subTest(surface=surface):
                # The CLI uses exit 2 for blocked replies, so produce the same
                # sealed recovery envelope via the public retention boundary.
                recovery = Configuration.retain_proposal({'state': 'blocked'}, original, now=now[0])
                self.assert_advice(recovery['retained_proposal'], 'guidance', False)
                result = invoke(recovery, 'Back')
                self.assert_advice(result, 'guidance', False)
                self.assertEqual(result['after'], original['after'])
                unchanged()

    def test_repeated_projection_never_restores_withheld_original_or_uses_sibling(self):
        for surface in ('library', 'cli'):
            for kind in ('guidance', 'rates'):
                with self.subTest(surface=surface, kind=kind):
                    invoke, now, original, unchanged = self.conversation(surface, kind)
                    now[0] = '2026-10-02T12:00:01Z'
                    expired = invoke(original, 'Explain Build')
                    withheld = deepcopy(expired['recommendations']['implementation']['withheld_evidence'])
                    now[0] = '2026-10-02T12:00:00Z'
                    repeated = invoke(expired, 'Presets')
                    advice = repeated['recommendations']['implementation']
                    self.assertEqual(advice['withheld_evidence'], withheld)
                    if kind == 'guidance':
                        self.assertIsNone(advice['choice'])
                    else:
                        self.assertIsNone(advice['cost']['rates'])
                        self.assertIsNone(advice['cost']['estimate'])
                    unchanged()

    def test_no_evidence_read_and_display_do_not_consume_extra_clock_values(self):
        dates = iter([fixtures.NOW, fixtures.NOW])
        service = Configuration(self.project, self.discover, lambda: next(dates), context=self.context)
        original = service.read()
        self.assertEqual(original['state'], 'decision_required')
        self.assertIsNone(original['recommendations']['implementation']['choice'])
        explained = service.reply(original, 'Explain Build')
        displayed = service.reply(explained, 'Presets')
        self.assertIsNone(displayed['recommendations']['implementation']['choice'])
        self.assertEqual(displayed['after'], original['after'])
        self.assertEqual(self.state.read_bytes(), self.original)

    def assert_rejected_claim_owner(self, result, original, selected):
        retained = result.get('retained_proposal', result)
        role = original['replacement']['role']
        self.assertEqual(retained['after'], original['after'])
        self.assertEqual(retained['before'], original['before'])
        self.assertNotIn('Accept replacement', retained['choices'])
        advice = retained['recommendations'][role]
        self.assertIsNone(advice['choice'])
        self.assertIsNone(advice['guidance'])
        self.assertIsNone(advice['cost'])
        for kind, claim in (('guidance', selected['guidance']), ('rates', selected['cost']['rates'])):
            # Status may change; original claim content and successful date may not.
            actual = advice['withheld_evidence'][kind]
            self.assertEqual({key: value for key, value in actual.items() if key != 'status'},
                             {key: value for key, value in claim.items() if key != 'status'})
        self.assertIn('Refresh', advice['limitations'])
        self.assertIn('editor', advice['limitations'])
        copies = [row['recommendation'] for row in retained['role_proposal'] if row['role'] == role]
        for owner, key in (('replacement', 'advice'), ('explanation', 'recommendation')):
            if retained.get(owner, {}).get('role') == role:
                copies.append(retained[owner][key])
        if isinstance(retained['recommended']['advice'], dict):
            copies.append(retained['recommended']['advice'][role])
        for copied in copies:
            self.assertEqual(copied, advice)
        return retained

    def test_rejected_divergent_copies_preserve_root_guidance_and_independent_price(self):
        for surface in ('library', 'cli'):
            for kind in ('guidance', 'rates'):
                invoke, now, original, unchanged = self.conversation(surface, kind)
                role = original['replacement']['role']
                selected = deepcopy(original['recommendations'][role])
                for age in (86399, 86400, 86401):
                    now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00'))
                              + timedelta(seconds=age)).isoformat()
                    for offset in (-1000, 1000):
                        with self.subTest(surface=surface, kind=kind, age=age, offset=offset):
                            draft = deepcopy(original)
                            nested = draft['replacement']['advice']
                            claim = nested['guidance'] if kind == 'guidance' else nested['cost']['rates']
                            claim['checked_at'] = (datetime.fromisoformat(claim['checked_at'].replace('Z', '+00:00'))
                                                   + timedelta(seconds=offset)).isoformat()
                            if kind == 'guidance':
                                claim['text'] = 'Different same-model task evidence'
                            else:
                                claim['input'] = 7
                            # Even a claim present in the source collection is not the selection.
                            draft['recommendation_evidence'][kind].append(deepcopy(claim))
                            draft['proposal_revision'] = Configuration._revision(draft)
                            untouched = deepcopy(draft)
                            rejected = invoke(draft, 'Accept replacement')
                            retained = self.assert_rejected_claim_owner(rejected, original, selected)
                            self.assertIn('Refresh', retained['choices'])
                            self.assertIn('Choose another model', retained['choices'])
                            for action in ('Accept replacement', 'Explain ' + role, 'Back', 'Explain ' + role):
                                retained = self.assert_rejected_claim_owner(invoke(retained, action), original, selected)
                            self.assertEqual(draft, untouched)
                            unchanged()

    def test_malformed_replacement_copy_never_overwrites_selected_root(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'guidance')
            role = original['replacement']['role']
            selected = deepcopy(original['recommendations'][role])
            for age in (86399, 86400, 86401):
                now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00'))
                          + timedelta(seconds=age)).isoformat()
                for malformed in (None, [], {}, {'choice': selected['choice']},
                                  {**selected, 'guidance': []}, {**selected, 'cost': []}):
                    with self.subTest(surface=surface, age=age, malformed=malformed):
                        draft = deepcopy(original)
                        draft['replacement']['advice'] = deepcopy(malformed)
                        draft['proposal_revision'] = Configuration._revision(draft)
                        result = self.assert_rejected_claim_owner(invoke(draft, 'Accept replacement'), original, selected)
                        result = self.assert_rejected_claim_owner(invoke(result, 'Accept replacement'), original, selected)
                        self.assert_rejected_claim_owner(invoke(result, 'Explain ' + role), original, selected)
                        unchanged()

    def test_partial_root_retains_its_claims_without_borrowing_nested_selection(self):
        for surface in ('library', 'cli'):
            invoke, now, original, unchanged = self.conversation(surface, 'guidance')
            role = original['replacement']['role']
            for missing in ('choice', 'limitations'):
                for action in ('Accept replacement', 'Back', ['invalid reply']):
                    with self.subTest(surface=surface, missing=missing, action=action):
                        draft = deepcopy(original)
                        selected = draft['recommendations'][role]
                        selected['guidance']['text'] = 'Root-owned original text'
                        selected.pop(missing)
                        expected = deepcopy(selected)
                        draft['proposal_revision'] = Configuration._revision(draft)
                        result = invoke(draft, action)
                        if missing == 'limitations' and action != 'Accept replacement':
                            # A nonessential display field does not invalidate fresh suitability.
                            retained = result.get('retained_proposal', result)
                            self.assertEqual(retained['recommendations'][role]['guidance']['text'],
                                             'Root-owned original text')
                        else:
                            self.assert_rejected_claim_owner(result, original, expected)
                        unchanged()

    def test_rejected_copy_recovers_only_through_explicit_editor_or_refresh(self):
        for surface in ('library', 'cli'):
            with self.subTest(surface=surface):
                invoke, now, original, unchanged = self.conversation(surface, 'guidance', keep_source=True)
                role = original['replacement']['role']
                selected = deepcopy(original['recommendations'][role])
                draft = deepcopy(original)
                draft['replacement']['advice']['guidance']['text'] = 'Divergent display copy'
                draft['proposal_revision'] = Configuration._revision(draft)
                now[0] = '2026-10-02T12:00:01Z'
                rejected = self.assert_rejected_claim_owner(invoke(draft, 'Accept replacement'), original, selected)
                editor = invoke(rejected, 'Choose another model')
                self.assertEqual(editor['step'], 'edit')
                self.assertEqual(editor['edit_role'], role)
                chosen = invoke(editor, '1')
                self.assertEqual(chosen['after'][role]['model_id'], 'fixture-code')
                self.assertIsNone(chosen['recommendations'][role]['choice'])
                unchanged()
                refreshed = invoke(rejected, 'Refresh')
                self.assertEqual(refreshed['after'], original['after'])
                self.assertIn('Accept replacement', refreshed['choices'])
                self.assertEqual(refreshed['recommendations'][role]['guidance']['text'], 'Younger sibling guidance')
                self.assertEqual(refreshed['personal'], original['personal'])
                accepted = invoke(refreshed, 'Accept replacement')
                self.assertEqual(accepted['after'][role]['model_id'], 'fixture-code')
                self.assertEqual(self.state.read_bytes(), self.original)
                self.assertFalse((self.project / '.playbook-config.json').exists())

    def test_cli_exception_recovery_is_total_for_malformed_nested_advice(self):
        invoke, now, original, unchanged = self.conversation('library', 'guidance')
        mutations = [None, [], 'invalid', {'choice': None, 'guidance': []},
                     {'choice': None, 'guidance': 'invalid'},
                     {'choice': None, 'cost': ['invalid']},
                     {'choice': None, 'cost': {'rates': ['invalid']}},
                     {'choice': None, 'withheld_evidence': ['invalid']},
                     {'choice': None, 'withheld_evidence': {'guidance': ['invalid']}},
                     {'choice': None, 'guidance': {'source_url': [], 'status': [], 'checked_at': []}}]
        for record in mutations:
            with self.subTest(record=record):
                draft = deepcopy(original)
                draft['recommendations']['implementation'] = record
                draft['proposal_revision'] = Configuration._revision(draft)
                # Missing reply exercises the CLI exception/retention path.
                process = subprocess.run([sys.executable, str(Path(__file__).with_name('configure-playbook.py')),
                                          '--project', str(self.project), '--now', now[0], 'reply'],
                                         input=json.dumps({'proposal': draft}), text=True, capture_output=True)
                self.assertEqual(process.returncode, 2, process.stderr)
                self.assertEqual(process.stderr, '')
                result = json.loads(process.stdout)
                self.assertEqual(result['state'], 'blocked')
                self.assertEqual(result['retained_proposal']['after'], original['after'])
                unchanged()


if __name__ == '__main__':
    unittest.main()
