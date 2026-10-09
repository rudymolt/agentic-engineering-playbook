"""Shared fixtures for the reviewed guidance test shards."""
from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_model_recommendations as fixtures
from model_recommendations import OfficialSources, SOURCES, load_reviewed_guidance, validate_reviewed_guidance
from playbook_config import Configuration, ROLES


HEADING = 'Choosing a model'
PARAGRAPH = ('If you\'re not sure where to start, use Fixture Code, our flagship model for complex reasoning and coding. '
             'Choose Fixture Analysis to balance intelligence and cost.')
ENTRY = {"model_id": "fixture-code", "provider": "openai", "label": "Fixture Code", "tasks": ["coding"],
         "risks": ["ordinary", "high"], "source_url": SOURCES[0], "heading": HEADING, "paragraph": PARAGRAPH,
         "link": "/api/docs/models/fixture-code", "reviewed_at": "2026-10-05"}
LINKED = ('If you&#x27;re not sure where to start, use <span><a href="/api/docs/models/fixture-code">Fixture Code</a></span>, '
          'our flagship model for complex reasoning and coding. Choose <a href="/api/docs/models/fixture-analysis">Fixture Analysis</a>'
          ' to balance intelligence and cost.')
PAGE = '<main><h1>Models</h1><div><h2>' + HEADING + '</h2><p>' + LINKED + '</p><p>All models support text input.</p></div></main>'
WITHDRAWN = 'provider wording changed since review'
RUBY_ENTRY = {**ENTRY, 'heading': 'Reviewed task choice',
              'paragraph': 'Compare Other first. Use Fixture Code for coding.'}
RUBY_PAGE = ('<h2>Reviewed task choice</h2><p>Compare <a href="/api/docs/models/other">Other</a> first. '
             'Use <a href="/api/docs/models/fixture-code"><em>Fixture Code</em></a> for coding.</p>')



class ReviewedGuidanceCase(unittest.TestCase):
    setUp = fixtures.RecommendationTests.setUp
    discover = fixtures.RecommendationTests.discover
    service = fixtures.RecommendationTests.service

    def retrieve(self, page, entries=(ENTRY,), url=SOURCES[0]):
        return OfficialSources(lambda: fixtures.NOW, fetch=lambda requested: page, reviewed=list(entries)).retrieve(urls=[url])

    def cli(self, action, request, source, cache):
        adapter = "import json,sys; r=json.load(sys.stdin); json.dump(dict(request_id=r['request_id'],checked_at=r['started_at'],authority='host-reported-selection',revision='fixture',routes=" + repr(self.routes) + "),sys.stdout)"
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('configure-playbook.py')),
                                 '--project', str(self.project), '--now', fixtures.NOW,
                                 '--evidence-fixture', str(source), '--evidence-dir', str(cache),
                                 '--discovery-command', json.dumps([sys.executable, '-c', adapter]), action],
                                input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def assert_page_contract(self, page, confirmed, entry=ENTRY):
        evidence = self.retrieve(page, entries=(entry,))
        with self.subTest(seam='OfficialSources'):
            self.assertEqual(bool(evidence['guidance']), confirmed)
            if not confirmed:
                self.assertIn(WITHDRAWN, evidence['sources'][0]['uncertainty'])
        service = self.service(sources=lambda: evidence)
        draft = service.read()
        with self.subTest(seam='Configuration'):
            self.assertEqual('Accept replacement' in draft['choices'], confirmed)
            accepted = service.reply(draft, 'Accept replacement')
            self.assertEqual(accepted['step'] == 'preview', confirmed)
            if not confirmed:
                self.assertEqual(accepted['after'], draft['after'])
        sample_cli = not getattr(self, '_page_cli_sampled', False)
        with tempfile.TemporaryDirectory() as temporary:
            source, cache = Path(temporary) / 'source.json', Path(temporary) / 'cache'
            source.write_text(json.dumps(evidence))
            if sample_cli:
                with self.subTest(seam='configure-playbook.py'):
                    cli_draft = self.cli('read', {'context': self.context}, source, cache)
                    self.assertEqual('Accept replacement' in cli_draft['choices'], confirmed)
                    cli_accepted = self.cli('reply', {'proposal': cli_draft, 'reply': 'Accept replacement'}, source, cache)
                    self.assertEqual(cli_accepted['step'] == 'preview', confirmed)
                    for key in ('after', 'choices', 'recommendations'):
                        self.assertEqual(cli_draft[key], draft[key])
                    for key in ('after', 'step', 'recommendations'):
                        self.assertEqual(cli_accepted[key], accepted[key])
                    if not confirmed:
                        self.assertEqual(cli_accepted['after'], cli_draft['after'])
            listing, html = Path(temporary) / 'guidance.json', Path(temporary) / 'page.html'
            listing.write_text(json.dumps({'schema_version': 1, 'entries': [entry]}))
            html.write_text(page)
            if sample_cli:
                with self.subTest(seam='check-model-guidance.py'):
                    result = subprocess.run([sys.executable, str(Path(__file__).with_name('check-model-guidance.py')),
                                             '--guidance', str(listing), '--page', SOURCES[0] + '=' + str(html)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0 if confirmed else 1, result.stdout + result.stderr)
                    self.assertIn('confirmed' if confirmed else WITHDRAWN, result.stdout)
                self._page_cli_sampled = True
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertFalse((self.project / '.playbook-config.json').exists())

    def assert_fresh_page_contract(self, page, confirmed, baseline=None, entry=ENTRY, pricing=False):
        baseline = PAGE if baseline is None else baseline
        self.assert_page_contract(page, confirmed, entry=entry)
        sample_cli = not getattr(self, '_fresh_cli_sampled', False)
        if pricing:
            rates = self.retrieve(page, entries=(entry,), url=SOURCES[2])['rates']
            self.assertEqual([(rate['input'], rate['output']) for rate in rates], [(0.75, 4.5)] if confirmed else [])
        with tempfile.TemporaryDirectory() as temporary:
            cache, log = Path(temporary) / 'cache', Path(temporary) / 'fetches'
            pages, fetched = {SOURCES[0]: baseline}, []
            if pricing:
                pages[SOURCES[2]] = baseline
            def fetch(url):
                fetched.append(url)
                return pages.get(url, '<p>Unknown</p>')
            official = OfficialSources(lambda: fixtures.NOW, fetch=fetch, reviewed=[entry])
            service = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                    recommendation_sources=official.retrieve, evidence_dir=Path(temporary) / 'service')
            original = service.read()
            cli_original = (self.official_cli('read', {'context': self.context}, cache, pages=pages,
                                              reviewed=[entry], now=fixtures.NOW) if sample_cli else deepcopy(original))
            self.assertIn('Accept replacement', original['choices'])
            self.assertIn('Accept replacement', cli_original['choices'])
            (self.project / 'approved.json').write_bytes(b'{"approved": "keep"}\n')
            approval_before = (self.project / 'approved.json').read_bytes()
            project_before = {path.name: path.read_bytes() for path in self.project.iterdir()}
            original_before, cli_before = deepcopy(original), deepcopy(cli_original)
            proposal_bytes = [json.dumps(proposal, sort_keys=True).encode() for proposal in (original, cli_original)]
            proposal_files = [Path(temporary) / name for name in ('proposal.json', 'cli-proposal.json')]
            for path, content in zip(proposal_files, proposal_bytes):
                path.write_bytes(content)
            cli_request = {'proposal': json.loads(proposal_files[1].read_bytes()), 'reply': 'Accept replacement'}
            cli_request_before = deepcopy(cli_request)
            pages[SOURCES[0]] = page
            if pricing:
                pages[SOURCES[2]] = page
            fetched.clear()
            accepted = service.reply(original, 'Accept replacement')
            self.assertEqual(fetched, [SOURCES[0]])
            cli_accepted = (self.official_cli('reply', cli_request, cache, pages=pages, reviewed=[entry],
                                              fetch_log=log, now=fixtures.NOW) if sample_cli else deepcopy(accepted))
            if sample_cli:
                self.assertEqual(log.read_text().splitlines(), [SOURCES[0]])
            for seam, proposal, result in (('Configuration fresh Accept', original, accepted),
                                           ('CLI fresh Accept', cli_original, cli_accepted)):
                with self.subTest(seam=seam):
                    self.assertEqual(result['step'] == 'preview', confirmed)
                    if confirmed:
                        self.assertEqual(result['after'][proposal['replacement']['role']]['model_id'], 'fixture-code')
                        for role in ROLES:
                            if role != proposal['replacement']['role']:
                                self.assertEqual(result['after'][role], proposal['after'][role])
                    else:
                        self.assertEqual(result['after'], proposal['after'])
                        self.assertNotIn('Accept replacement', result['choices'])
                        self.assertIn(WITHDRAWN, result['message'])
                        self.assertIsNone(result['recommendations'][proposal['replacement']['role']]['choice'])
                        self.assertEqual(result['replacement']['role'], proposal['replacement']['role'])
                        self.assertEqual(result['step'], proposal['step'])
                    self.assertFalse(result['launched'])
            self.assertEqual(original, original_before)
            self.assertEqual(cli_original, cli_before)
            self.assertEqual([json.dumps(proposal, sort_keys=True).encode() for proposal in (original, cli_original)], proposal_bytes)
            self.assertEqual([path.read_bytes() for path in proposal_files], proposal_bytes)
            self.assertEqual(cli_request, cli_request_before)
            self.assertEqual((self.project / 'approved.json').read_bytes(), approval_before)
            self.assertEqual({path.name: path.read_bytes() for path in self.project.iterdir()}, project_before)
            # Fresh reads use the actual HTTP adapter, in separate CLI processes.
            fresh = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                  recommendation_sources=official.retrieve).read()
            cli_fresh = (self.official_cli('read', {'context': self.context}, Path(temporary) / 'fresh',
                                           pages=pages, reviewed=[entry], now=fixtures.NOW)
                         if sample_cli else deepcopy(fresh))
            for draft in (fresh, cli_fresh):
                self.assertEqual('Accept replacement' in draft['choices'], confirmed)
                self.assertEqual(bool(draft['recommendation_evidence']['guidance']), confirmed)
                if pricing:
                    rates = draft['recommendation_evidence']['rates']
                    self.assertEqual([(rate['input'], rate['output']) for rate in rates], [(0.75, 4.5)] if confirmed else [])
                    if confirmed:
                        self.assertAlmostEqual(draft['recommendations']['implementation']['cost']['estimate']['amount'], 0.02025)
            self.assertEqual((self.project / 'approved.json').read_bytes(), approval_before)
            self.assertEqual({path.name: path.read_bytes() for path in self.project.iterdir()}, project_before)
            if sample_cli:
                self._fresh_cli_sampled = True

    def assert_ruby_contract(self, page, confirmed):
        with patch.object(fixtures, 'NOW', '2026-10-06T00:00:00Z'):
            self.assert_fresh_page_contract(page, confirmed, baseline=RUBY_PAGE, entry=RUBY_ENTRY)

    def official_cli(self, action, request, cache, expected_code=0, pages=None, reviewed=None, now=fixtures.NOW, listing=None,
                     fail_cache_write=False, fetch_log=None):
        # Run the public entry point with only its clock and HTTP boundary controlled.
        bootstrap = ("import runpy,sys\nfrom unittest.mock import patch\n"
                     "sys.path.insert(0, " + repr(str(Path(__file__).resolve().parent)) + ")\n"
                     "from model_recommendations import load_reviewed_guidance as original_loader\n"
                     "from datetime import datetime as real_datetime\nfrom contextlib import nullcontext\nimport playbook_config\n"
                     "class Clock(real_datetime):\n @classmethod\n def now(cls, tz=None): return real_datetime.fromisoformat(" + repr(now.replace('Z', '+00:00')) + ")\n"
                     "def fetch(url):\n" +
                     (" with open(" + repr(str(fetch_log)) + ", 'a') as log: log.write(url + '\\n')\n" if fetch_log else "") +
                     (" raise OSError('Controlled source unavailable')\n" if pages is None else " return " + repr(pages) + ".get(url, '<p>Unknown</p>')\n") +
                     "cache_patch = " + ("patch('model_evidence_cache.os.replace', side_effect=OSError('Controlled persistence failure'))" if fail_cache_write else "nullcontext()") + "\n" +
                     "with cache_patch, patch('playbook_config.datetime', Clock), patch('model_recommendations.datetime', Clock), patch('model_recommendations.OfficialSources._fetch', side_effect=fetch), " +
                     "patch('model_recommendations.load_reviewed_guidance', " +
                     ("side_effect=lambda: original_loader(" + repr(str(listing)) + ")" if listing else
                      "return_value=" + repr(load_reviewed_guidance() if reviewed is None else reviewed)) + "):\n"
                     " script = sys.argv.pop(1); sys.argv[0] = script\n"
                     " runpy.run_path(script, run_name='__main__')\n")
        adapter = "import json,sys; r=json.load(sys.stdin); json.dump(dict(request_id=r['request_id'],checked_at=r['started_at'],authority='host-reported-selection',revision='fixture',routes=" + repr(self.routes) + "),sys.stdout)"
        script = str(Path(__file__).resolve().with_name('configure-playbook.py'))
        # The bootstrap removes its script argument before entering the public CLI.
        result = subprocess.run([sys.executable, '-c', bootstrap, script, '--project', str(self.project),
                                 '--evidence-dir', str(cache), '--discovery-command', json.dumps([sys.executable, '-c', adapter]), action],
                                input=json.dumps(request), text=True, capture_output=True, cwd=cache.parent,
                                env={**os.environ, 'PYTHONPATH': os.environ.get('PYTHONPATH', '').split(os.pathsep)[0]})
        self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def assert_withdrawn(self, page, entries=(ENTRY,), url=SOURCES[0]):
        evidence = self.retrieve(page, entries, url)
        self.assertEqual(evidence['guidance'], [])
        self.assertIn(WITHDRAWN, evidence['sources'][0]['uncertainty'])
        self.assertIn('fixture-code', evidence['sources'][0]['uncertainty'])
        service = self.service(sources=lambda: evidence)
        draft = service.read()
        self.assertNotIn('Accept replacement', draft['choices'])
        self.assertEqual(service.reply(draft, 'Accept replacement')['after'], draft['after'])
        self.assertEqual(service.reply(draft, 'Not now')['state'], 'unchanged')
        self.assertEqual(self.state.read_bytes(), self.original)
