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

    def conversation(self, surface, kind):
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
                self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
                return json.loads(process.stdout)
        original = invoke()
        if surface == 'cli':
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
            self.assertIn(fixtures.NOW, json.dumps(advice))
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
