"""S7a reviewed provider guidance: the edition list is authoritative; pages only confirm it."""
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


class ReviewedGuidanceTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as temporary:
            source, cache = Path(temporary) / 'source.json', Path(temporary) / 'cache'
            source.write_text(json.dumps(evidence))
            with self.subTest(seam='configure-playbook.py'):
                draft = self.cli('read', {'context': self.context}, source, cache)
                self.assertEqual('Accept replacement' in draft['choices'], confirmed)
                accepted = self.cli('reply', {'proposal': draft, 'reply': 'Accept replacement'}, source, cache)
                self.assertEqual(accepted['step'] == 'preview', confirmed)
                if not confirmed:
                    self.assertEqual(accepted['after'], draft['after'])
            listing, html = Path(temporary) / 'guidance.json', Path(temporary) / 'page.html'
            listing.write_text(json.dumps({'schema_version': 1, 'entries': [entry]}))
            html.write_text(page)
            with self.subTest(seam='check-model-guidance.py'):
                result = subprocess.run([sys.executable, str(Path(__file__).with_name('check-model-guidance.py')),
                                         '--guidance', str(listing), '--page', SOURCES[0] + '=' + str(html)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if confirmed else 1, result.stdout + result.stderr)
                self.assertIn('confirmed' if confirmed else WITHDRAWN, result.stdout)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertFalse((self.project / '.playbook-config.json').exists())

    def test_empty_intervening_blocks_withdraw_but_layout_wrappers_confirm(self):
        for block in ('<p></p>', '<hr>', '<div></div>', '<div><p> </p></div>'):
            with self.subTest(block=block):
                self.assert_page_contract(PAGE.replace('</h2>', '</h2>' + block), False)
        paragraph = '<p>' + LINKED + '</p>'
        self.assert_page_contract(PAGE.replace(paragraph, '<section><div>' + paragraph + '</div></section>'), True)

    def test_inert_templates_cannot_confirm_heading_paragraph_or_link(self):
        paragraph = '<p>' + LINKED + '</p>'
        link = '<a href="/api/docs/models/fixture-code">Fixture Code</a>'
        pages = ('<template>' + PAGE + '</template>',
                 PAGE.replace(paragraph, '<template>' + paragraph + '</template>'),
                 PAGE.replace('<h2>' + HEADING + '</h2>', '<template><h2>' + HEADING + '</h2></template>'),
                 PAGE.replace(link, 'Fixture Code<template><a href="/api/docs/models/fixture-code"></a></template>'),
                 '<template><template><p>Unused</p></template>' + PAGE + '</template>',
                 '<template><style>unused</style><script>unused</script>' + PAGE + '</template>',
                 '<template></style>' + PAGE + '</template>')
        with tempfile.TemporaryDirectory() as temporary:
            positive = self.official_cli('read', {'context': self.context}, Path(temporary) / 'positive',
                                         pages={SOURCES[0]: PAGE}, reviewed=[ENTRY])
            self.assertIn('Accept replacement', positive['choices'])
            for index, page in enumerate(pages):
                with self.subTest(page=page):
                    self.assert_page_contract(page, False)
                    draft = self.official_cli('read', {'context': self.context}, Path(temporary) / str(index),
                                              pages={SOURCES[0]: page}, reviewed=[ENTRY])
                    self.assertNotIn('Accept replacement', draft['choices'])
                    refused = self.official_cli('reply', {'proposal': draft, 'reply': 'Accept replacement'},
                                                Path(temporary) / str(index), pages={SOURCES[0]: page}, reviewed=[ENTRY])
                    self.assertEqual(refused['after'], draft['after'])

    def test_template_self_closing_flag_does_not_render_its_descendants(self):
        self.assert_page_contract('<template/>' + PAGE + '</template>', False)
        self.assert_page_contract('<template />' + PAGE, False)
        self.assert_page_contract('<template>' + PAGE + '</template>' + PAGE.replace('our flagship', 'our retired'), False)
        self.assert_page_contract('<template><p>Unused inert copy</p></template>' + PAGE, True)

    def assert_fresh_page_contract(self, page, confirmed, baseline=None, entry=ENTRY, pricing=False):
        baseline = PAGE if baseline is None else baseline
        self.assert_page_contract(page, confirmed, entry=entry)
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
            cli_original = self.official_cli('read', {'context': self.context}, cache, pages=pages, reviewed=[entry], now=fixtures.NOW)
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
            cli_accepted = self.official_cli('reply', cli_request, cache,
                                             pages=pages, reviewed=[entry], fetch_log=log, now=fixtures.NOW)
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
            cli_fresh = self.official_cli('read', {'context': self.context}, Path(temporary) / 'fresh',
                                        pages=pages, reviewed=[entry], now=fixtures.NOW)
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

    def assert_ruby_contract(self, page, confirmed):
        with patch.object(fixtures, 'NOW', '2026-10-06T00:00:00Z'):
            self.assert_fresh_page_contract(page, confirmed, baseline=RUBY_PAGE, entry=RUBY_ENTRY)

    def test_hidden_forbidden_descendant_refuses_fresh_acceptance_at_all_seams(self):
        entry = {**RUBY_ENTRY, 'heading': 'Reviewed boundary choice'}
        baseline = RUBY_PAGE.replace(RUBY_ENTRY['heading'], entry['heading'])
        page = baseline.replace('</p>', '<q hidden>Quoted qualification</q></p>')
        with patch.object(fixtures, 'NOW', '2026-10-06T00:00:00Z'):
            self.assert_fresh_page_contract(page, False, baseline=baseline, entry=entry)

    def test_forbidden_descendants_remain_excluded_when_visibility_is_inherited(self):
        for tag in ('del', 's', 'strike', 'blockquote', 'q'):
            for fragment in ('<' + tag + ' hidden>unused</' + tag + '>',
                             '<span hidden><' + tag + '>unused</' + tag + '></span>',
                             '<dialog><' + tag + '>unused</' + tag + '></dialog>',
                             '<details><summary> </summary><' + tag + '>unused</' + tag + '></details>'):
                for closing in ('</h2>', '</p>', '</em>'):
                    with self.subTest(tag=tag, fragment=fragment, closing=closing):
                        self.assert_ruby_contract(RUBY_PAGE.replace(closing, fragment + closing), False)

    def test_forbidden_descendants_preserve_nonvoid_and_malformed_boundaries(self):
        for tag in ('del', 's', 'strike', 'blockquote', 'q'):
            for fragment in ('<' + tag + ' hidden/>unused</' + tag + '>',
                             '<span hidden/><' + tag + '/>unused</' + tag + '></span>',
                             '<span hidden><' + tag + '><i>unused</span></' + tag + '>',
                             '<' + tag + ' hidden>unused</other>'):
                with self.subTest(tag=tag, fragment=fragment):
                    self.assert_ruby_contract(RUBY_PAGE.replace('</p>', fragment + '</p>'), False)

    def test_apparent_forbidden_tokens_in_literal_or_inert_bodies_do_not_exclude_units(self):
        for tag in ('del', 's', 'strike', 'blockquote', 'q'):
            token = '<' + tag + ' hidden>unused</' + tag + '>'
            for container in ('script', 'style', 'textarea', 'title', 'noscript', 'template'):
                fragment = '<' + container + '/>' + token + '</' + container + '>'
                with self.subTest(tag=tag, container=container):
                    self.assertTrue(self.retrieve(RUBY_PAGE.replace('</p>', fragment + '</p>'),
                                                  entries=(RUBY_ENTRY,))['guidance'])
        for closing in ('</h2>', '</p>', '</em>'):
            for fragment in ('<script/><q hidden>unused</q></script>',
                             '<textarea/><strike hidden>unused</strike></textarea>',
                             '<template/><span hidden><blockquote>unused</blockquote></span></template>'):
                self.assert_ruby_contract(RUBY_PAGE.replace(closing, fragment + closing), True)

    def test_hidden_forbidden_siblings_do_not_poison_clean_units_or_pricing(self):
        for tag in ('del', 's', 'strike', 'blockquote', 'q'):
            fragment = '<span hidden><' + tag + '>unused</' + tag + '></span>'
            for page in ('<section>' + fragment + RUBY_PAGE + '</section>',
                         '<p>Unrelated' + fragment + '</p>' + RUBY_PAGE,
                         RUBY_PAGE.replace('</h2>', '</h2>' + fragment),
                         RUBY_PAGE.replace('</h2>', fragment + '</h2>') + RUBY_PAGE):
                self.assert_ruby_contract(page, True)
            sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
            rates = self.retrieve(sample.replace('$0.75', '$0.75' + fragment), url=SOURCES[2])['rates']
            self.assertEqual([(rate['input'], rate['output']) for rate in rates], [(0.75, 4.5)])
        for closing in ('</h2>', '</p>', '</em>'):
            self.assert_ruby_contract(RUBY_PAGE.replace(closing, '<span hidden>unused</span>' + closing), True)
        self.assert_ruby_contract(RUBY_PAGE.replace('</h2>', '</h2><div hidden><p>Unused</p></div>'), True)

    def test_eof_literal_less_than_cannot_confirm_reviewed_paragraph(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        self.assert_ruby_contract(RUBY_PAGE.removesuffix('</p>') + '<', False)

    def test_eof_character_references_participate_in_reviewed_text(self):
        opened = RUBY_PAGE.removesuffix('</p>')
        for suffix, confirmed in (('</', False), ('&amp', False), ('&#60', False),
                                  ('&#x3c', False), ('&unknown', False),
                                  ('&nbsp', True), ('&#32', True), ('&#8203', True)):
            with self.subTest(suffix=suffix):
                self.assert_ruby_contract(opened + suffix, confirmed)
        self.assert_ruby_contract(opened.removesuffix('.') + '&#46', True)

    def test_eof_unclosed_visible_required_link_keeps_text_and_references(self):
        # The required model link follows another link and remains open at EOF.
        opened = RUBY_PAGE.replace('</em></a> for coding.</p>', '</em> for coding.')
        for suffix, confirmed in (('', True), ('<', False), ('&amp', False),
                                  ('&nbsp', True), ('</a', True)):
            with self.subTest(suffix=suffix):
                self.assert_ruby_contract(opened + suffix, confirmed)
        self.assert_ruby_contract(opened.removesuffix('.') + '&#x2e', True)

    def test_eof_truncated_native_markup_is_discarded_without_visible_text(self):
        opened = RUBY_PAGE.removesuffix('</p>')
        for token in ('<span', '<span hidden="', '<a href="/api/docs/models/other',
                      '</p', '</p ', '<!-- Only for preview', '<!-', '<!',
                      '<!DOCTYPE html', '<![CDATA[Only for preview', '<?provider'):
            with self.subTest(token=token):
                self.assert_ruby_contract(opened + token, True)

    def test_eof_heading_without_successor_cannot_confirm(self):
        heading = RUBY_PAGE.split('</h2>')[0]
        for suffix in ('', '<', '&amp', '&#32', '<span', '<!--'):
            with self.subTest(suffix=suffix):
                self.assert_ruby_contract(heading + suffix, False)

    def test_eof_hidden_raw_inert_and_foreign_copies_remain_excluded(self):
        opened = RUBY_PAGE.removesuffix('</p>')
        for prefix in ('<span hidden>', '<template>', '<script>', '<textarea>'):
            with self.subTest(prefix=prefix):
                self.assert_ruby_contract(opened + prefix + '&amp<', True)
        # plaintext ends the native paragraph; retain the existing interruption barrier.
        self.assert_ruby_contract(opened + '<plaintext>&amp<', False)
        for prefix in ('<div hidden>', '<template>', '<script>', '<textarea>',
                       '<svg><foreignObject>', '<math><mtext>', '<select><option>'):
            with self.subTest(prefix=prefix):
                self.assert_ruby_contract(prefix + opened + '&amp', False)

    def test_eof_pricing_preserves_complete_tables_and_refuses_truncated_context(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(rate['input'], rate['output']) for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for suffix in ('<', '&amp', '<span', '<!--', '<!DOCTYPE', '<?provider'):
            with self.subTest(suffix=suffix):
                self.assertEqual(rates(sample + suffix), [(0.75, 4.5)])
                self.assertEqual(rates(sample.removesuffix('</td></tr></table>') + suffix), [])
        for prefix in ('<h2>Standard', '<p>Prices in USD per 1M tokens',
                       '<a href="/api/docs/models/fixture-code">fixture-code',
                       sample.removesuffix('</td></tr></table>')):
            for suffix in ('<', '&amp', '&#46', '<!--'):
                with self.subTest(prefix=prefix, suffix=suffix):
                    self.assertEqual(rates(prefix + suffix), [])

    def test_native_br_end_separates_reviewed_required_link_words(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        self.assert_ruby_contract(RUBY_PAGE.replace('Fixture Code</em>', 'Fi</br>xture Code</em>'), False)

    def test_native_br_starts_and_ends_preserve_word_boundaries_in_reviewed_units(self):
        for token in ('<br>', '<br/>', '</br>', '</BR >', '</br hidden>'):
            for text, split in (('Reviewed', 'Revi' + token + 'ewed'),
                                ('Compare', 'Com' + token + 'pare'),
                                ('Fixture Code</em>', 'Fi' + token + 'xture Code</em>')):
                with self.subTest(token=token, text=text):
                    self.assert_ruby_contract(RUBY_PAGE.replace(text, split), False)

    def test_native_br_starts_and_ends_between_words_keep_reviewed_text(self):
        for token in ('<br>', '<br/>', '</br>', '</BR >', '</br hidden>'):
            page = RUBY_PAGE.replace('Reviewed task', 'Reviewed' + token + 'task')
            page = page.replace('Other</a> first', 'Other</a>' + token + 'first')
            page = page.replace('Fixture Code</em>', 'Fixture' + token + 'Code</em>')
            with self.subTest(token=token):
                self.assert_ruby_contract(page, True)

    def test_native_br_separator_respects_hidden_raw_inert_and_excluded_context(self):
        for addition in ('<span hidden></br></span>', '<br hidden>', '<br hidden/>',
                         '<template/></br></template>', '<script></br></script>',
                         '<textarea></br></textarea>', '<!-- </br> -->'):
            with self.subTest(addition=addition):
                self.assert_ruby_contract(RUBY_PAGE.replace('Fixture Code</em>', 'Fi' + addition + 'xture Code</em>'), True)
        self.assert_ruby_contract(RUBY_PAGE.replace('Fixture Code</em>', 'Fi<del></br></del>xture Code</em>'), False)
        self.assert_ruby_contract('<div hidden>' + RUBY_PAGE.replace('Reviewed', 'Re</br>viewed') + '</div>', False)

    def test_native_br_end_does_not_release_select_foreign_or_inert_copies(self):
        for opening, closing in (('<select><option>', '</option></select>'),
                                 ('<svg><foreignObject>', '</foreignObject></svg>'),
                                 ('<math><mtext>', '</mtext></math>'),
                                 ('<template/>', '</template>')):
            with self.subTest(scope=opening):
                self.assert_ruby_contract(opening + '</br>' + RUBY_PAGE + closing, False)
                self.assert_ruby_contract(opening + '</br>' + closing + RUBY_PAGE, True)
        prefix = '<template><svg><foreignObject><select></foreignObject></br><![CDATA[>'
        self.assert_ruby_contract(prefix + '</select></foreignObject></svg></template>' + RUBY_PAGE + ']]>', True)

    def test_native_br_start_end_pricing_separator_parity(self):
        prices = ('<p>Prices in USD per 1M tokens</p><h2>Standard</h2><p>Short context</p>'
                  '<table><tr><th>Model</th><th>Input</th><th>Cached input</th><th>Output</th></tr>'
                  '<tr><td>fixture-code</td><td>$0.75</td><td>$0.05</td><td>$4.50</td></tr></table>')
        def rates(page):
            return [(rate['input'], rate['output']) for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(prices), [(0.75, 4.5)])
        for token in ('<br>', '<br/>', '</br>', '</BR >', '</br hidden>'):
            with self.subTest(token=token):
                self.assertEqual(rates(prices.replace('Short context', 'Short' + token + 'context')), [(0.75, 4.5)])
                for text, split in (('Standard', 'Stan' + token + 'dard'),
                                    ('1M tokens', '1' + token + 'M tokens'),
                                    ('fixture-code', 'fixture-' + token + 'code'),
                                    ('$0.75', '$0.' + token + '75')):
                    self.assertEqual(rates(prices.replace(text, split)), [])
        for addition in ('<span hidden></br></span>', '<br hidden/>', '<template></br></template>',
                         '<textarea></br></textarea>'):
            self.assertEqual(rates(prices.replace('$0.75', '$0.75' + addition)), [(0.75, 4.5)])

    def test_native_cdata_bogus_comment_cannot_erase_visible_paragraph_qualifier(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        page = RUBY_PAGE.replace('</p>', '<![CDATA[> Only for preview accounts.]]></p>')
        self.assert_ruby_contract(page, False)

    def test_native_template_bogus_declaration_close_preserves_visible_successor(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        self.assert_ruby_contract('<template><![CDATA[></template>' + RUBY_PAGE + ' ]]>', True)

    def test_native_select_declarations_preserve_visible_successors(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        for opening, closing in (('<select><svg>', '</select>'),
                                 ('<template><select><xmp>', '</template>')):
            with self.subTest(scope=opening):
                self.assert_ruby_contract(opening + '<![CDATA[>' + closing + RUBY_PAGE + ' ]]>', True)

    def test_ignored_foreign_end_in_native_select_preserves_visible_successor(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        page = ('<template><svg><foreignObject><select></foreignObject><![CDATA[>'
                '</select></foreignObject></svg></template>' + RUBY_PAGE + ']]>')
        self.assert_ruby_contract(page, True)

    def test_select_ignored_ends_retain_native_declarations_in_integration_descendants(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        integrations = (('<svg><foreignObject>', '</foreignObject></svg>'),
                        ('<svg><desc>', '</desc></svg>'), ('<svg><title>', '</title></svg>'),
                        ('<math><mi>', '</mi></math>'), ('<math><mtext>', '</mtext></math>'),
                        ('<math><annotation-xml encoding="text/html">', '</annotation-xml></math>'))
        for opening, ending in integrations:
            for children in ('', '<option>', '<optgroup><option>'):
                with self.subTest(integration=opening, children=children):
                    prefix = '<template>' + opening + '<select>' + children + ending
                    self.assert_ruby_contract(prefix + '<![CDATA[></select>' + ending + '</template>' + RUBY_PAGE + ']]>', True)

    def test_select_option_and_optgroup_ends_preserve_native_and_genuine_foreign_boundaries(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        children = ('</option></optgroup></div></p></br></table></body></html></script>',
                    '<option></optgroup></option>', '<optgroup><option></optgroup></option>',
                    '<optgroup></option></optgroup>', '<option></option></option>',
                    '<optgroup><option></option></optgroup></optgroup>',
                    '<xmp></xmp><plaintext></plaintext>')
        ending = '</foreignObject></svg></template>'
        for child in children:
            with self.subTest(children=child):
                prefix = '<template><svg><foreignObject><select>' + child + '</foreignObject>'
                self.assert_ruby_contract(prefix + '<![CDATA[></select>' + ending + RUBY_PAGE + ']]>', True)
                # A genuine select close restores foreign CDATA: apparent
                # ancestor closes and the reviewed copy are still CDATA text.
                page = prefix + '</select><![CDATA[>' + ending + RUBY_PAGE + ']]>' + ending
                self.assert_ruby_contract(page, False)
                self.assert_ruby_contract(page + RUBY_PAGE, True)

    def test_select_declarations_retain_raw_inert_hidden_and_ambiguity_exclusions(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        ending = '</select></foreignObject></svg></template>'
        prefix = '<template><svg><foreignObject><select></foreignObject>'
        for tag in ('script', 'template'):
            with self.subTest(descendant=tag):
                page = prefix + '<' + tag + '></select><![CDATA[>' + ending + RUBY_PAGE + ']]></' + tag + '>' + ending
                self.assert_ruby_contract(page, False)
                self.assert_ruby_contract(page + RUBY_PAGE, True)
        closed = prefix + '<![CDATA[>' + ending
        self.assert_ruby_contract('<div hidden>' + closed + RUBY_PAGE + ']]></div>', False)
        self.assert_ruby_contract('<div hidden>' + closed + ']]></div>' + RUBY_PAGE, True)
        self.assert_ruby_contract(prefix + '<![CDATA[>' + RUBY_PAGE + ']]>' + ending, False)
        self.assert_ruby_contract(RUBY_PAGE.replace('</p>', closed + ' Only in preview.]]></p>'), False)

    def test_select_declaration_successors_and_foreign_copies_preserve_pricing_at_public_seams(self):
        sample = RUBY_PAGE + fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        ending = '</select></foreignObject></svg></template>'
        prefix = '<template><svg><foreignObject><select><optgroup><option></foreignObject>'
        foreign_end = '</foreignObject></svg></template>'
        pages = ((sample, True), (prefix + '<![CDATA[>' + ending + sample + ']]>', True),
                 (prefix + '</select><![CDATA[>' + foreign_end + sample + ']]>' + foreign_end, False),
                 ('<div hidden>' + prefix + '<![CDATA[>' + ending + sample + ']]></div>', False),
                 (prefix + '<script><![CDATA[>' + ending + sample + ']]></script>' + ending, False))
        context = {**self.context, 'workload': {'input_tokens': 3000, 'output_tokens': 1000, 'retries': 2,
                                              'billing_route': 'standard-short-context-uncached'}}
        with patch.object(fixtures, 'NOW', '2026-10-06T00:00:00Z'), patch.object(self, 'context', context):
            for page, confirmed in pages:
                with self.subTest(page=page):
                    self.assert_fresh_page_contract(page, confirmed, baseline=sample, entry=RUBY_ENTRY, pricing=True)

    def test_native_template_declarations_follow_ignored_select_tokens_and_foreign_end_breakouts(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        for opening in ('<template><svg></p>', '<template><svg></br>',
                        '<template><select><option><svg>', '<template><select><optgroup><svg>'):
            with self.subTest(scope=opening):
                self.assert_ruby_contract(opening + '<![CDATA[></template>' + RUBY_PAGE + ' ]]>', True)

    def test_native_inert_declarations_preserve_nested_hidden_and_malformed_successors(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        openings = ('<template>', '<template/><template>', '<template><div></span>',
                    '<div hidden><template>', '<template><svg/>',
                    '<template><svg><template/></svg>', '<template><svg><font color="red">',
                    '<template><svg><g></svg>', '<template><svg><foreignObject><span>',
                    '<template><math><mtext><span>',
                    '<template><math><annotation-xml encoding="text/html"><span>')
        for opening in openings:
            with self.subTest(scope=opening):
                ending = '</template>' * (2 if opening == '<template/><template>' else 1)
                if opening.startswith('<div hidden>'):
                    ending += '</div>'
                self.assert_ruby_contract(opening + '<![CDATA[>' + ending + RUBY_PAGE + ' ]]>', True)
        for token in ('<![cdata[>', '<![INCLUDE[>', '<![unknown>', '<!--><!---><!-- ignored -->'):
            with self.subTest(token=token):
                self.assert_ruby_contract('<template>' + token + '</template>' + RUBY_PAGE, True)
        self.assert_ruby_contract('<template><![CDATA[>' + RUBY_PAGE + ' ]]>', False)
        self.assert_ruby_contract('<template><template><![CDATA[></template>' + RUBY_PAGE + ' ]]></template>', False)
        self.assert_ruby_contract(RUBY_PAGE.replace('</p>', '<template><![CDATA[></template> Only for preview.]]></p>'), False)

    def test_foreign_cdata_inside_inert_templates_cannot_release_confirming_copies(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        scopes = (('<svg><g>', '</g></svg>'), ('<math><mrow>', '</mrow></math>'),
                  ('<svg><font>', '</font></svg>'), ('<svg><template>', '</template></svg>'),
                  ('<math><mtext><mglyph>', '</mglyph></mtext></math>'),
                  ('<svg><foreignObject>', '</foreignObject></svg>'),
                  ('<math><mtext>', '</mtext></math>'),
                  ('<math><annotation-xml encoding>', '</annotation-xml></math>'),
                  ('<math><annotation-xml encoding="text/html">', '</annotation-xml></math>'),
                  ('<svg><foreignObject><svg><g>', '</g></svg></foreignObject></svg>'))
        for opening, ending in scopes:
            with self.subTest(scope=opening):
                page = '<template>' + opening + '<![CDATA[>' + ending + '</template>' + RUBY_PAGE + ' ]]>' + ending + '</template>'
                self.assert_ruby_contract(page, False)
                self.assert_ruby_contract(page + RUBY_PAGE, True)

    def test_foreign_template_own_closes_cannot_release_native_inert_copies(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        for opening, ending in (('<svg><template></template>', '</svg>'),
                                ('<math><template></template>', '</math>'),
                                ('<svg><template/>', '</svg>')):
            with self.subTest(scope=opening):
                page = '<template>' + opening + RUBY_PAGE + ending + '</template>'
                self.assert_ruby_contract(page, False)
                self.assert_ruby_contract(page + RUBY_PAGE, True)

    def test_duplicate_encoding_cannot_change_inert_declaration_namespace(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        page = ('<template><math><annotation-xml encoding="application/xml" encoding="text/html">'
                '<template><![CDATA[></template>unused ]]></template>' + RUBY_PAGE
                + '</annotation-xml></math></template>')
        self.assert_ruby_contract(page, False)
        self.assert_ruby_contract(page + RUBY_PAGE, True)
        page = ('<template><math><annotation-xml encoding="text/html" encoding="application/xml">'
                '<template><![CDATA[></template></template>' + RUBY_PAGE + ' ]]>')
        self.assert_ruby_contract(page, True)

    def test_annotation_xml_svg_transition_preserves_native_template_successors(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        opening = '<template><math><annotation-xml><svg><foreignObject>'
        ending = '</foreignObject></svg></annotation-xml></math></template>'
        successor = '<template><![CDATA[></template></template>'
        self.assert_ruby_contract(opening + successor + RUBY_PAGE + ' ]]>', True)
        page = opening + '<![CDATA[>' + ending + RUBY_PAGE + ' ]]>' + ending
        self.assert_ruby_contract(page, False)
        self.assert_ruby_contract(page + RUBY_PAGE, True)
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(rate['input'], rate['output']) for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        self.assertEqual(rates(opening + successor + sample + ' ]]>'), [(0.75, 4.5)])
        self.assertEqual(rates(opening + '<![CDATA[>' + ending + sample + ' ]]>' + ending), [])

    def test_declaration_context_retains_native_raw_bodies_and_foreign_cdata(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        for tag in ('script', 'style', 'textarea', 'title', 'xmp'):
            with self.subTest(native_raw=tag):
                page = '<template><' + tag + '><![CDATA[></template>' + RUBY_PAGE + ' ]]></' + tag + '></template>'
                self.assert_ruby_contract(page, False)
                self.assert_ruby_contract(page + RUBY_PAGE, True)
        for tag in ('script', 'style', 'title'):
            with self.subTest(foreign=tag):
                ending = '</' + tag + '></svg></template>'
                page = '<template><svg><' + tag + '><![CDATA[>' + ending + RUBY_PAGE + ' ]]>' + ending
                self.assert_ruby_contract(page, False)
                self.assert_ruby_contract(page + RUBY_PAGE, True)

    def test_inert_declaration_context_preserves_pricing_positives_and_negatives(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(rate['input'], rate['output']) for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for opening in ('<template>', '<template><svg/>', '<div hidden><template>'):
            ending = '</template>' + ('</div>' if opening.startswith('<div hidden>') else '')
            self.assertEqual(rates(opening + '<![CDATA[>' + ending + sample + ' ]]>'), [(0.75, 4.5)])
        for opening, ending in (('<svg><g>', '</g></svg>'), ('<math><mrow>', '</mrow></math>'),
                                ('<svg><script>', '</script></svg>')):
            page = '<template>' + opening + '<![CDATA[>' + ending + '</template>' + sample + ' ]]>' + ending + '</template>'
            self.assertEqual(rates(page), [])
            self.assertEqual(rates(page + sample), [(0.75, 4.5)])

    def test_declaration_boundaries_retain_foreign_and_inert_exclusions(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        for opening, close, ending in (('<svg>', '</svg>', '</svg>'),
                                        ('<math>', '</math>', '</math>'),
                                        ('<template><svg>', '</template></svg>', '</svg></template>')):
            with self.subTest(scope=opening):
                # A close-like token in foreign CDATA is text, including in
                # an inert template. It cannot release a confirming copy.
                page = opening + '<![CDATA[>' + close + RUBY_PAGE + ']]>' + ending
                self.assert_ruby_contract(page, False)
                self.assert_ruby_contract(page + RUBY_PAGE, True)

    def test_native_declarations_comments_and_processing_instructions_preserve_visible_positives(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        tokens = ('<![CDATA[unused>', '<![CDATA[unused]]>', '<![cdata[unused>', '<![CdAtA[unused>',
                  '<![INCLUDE[unused>', '<![IGNORE[unused>', '<![if unused]>', '<![unknown unused>',
                  '<!unused "quoted>', '<?unused?>', '<!DOCTYPE html>', '<!DoCtYpE html>',
                  '<!-- unused > <p>not markup</p> -->', '<!-->', '<!--->', '<!--unused--!>')
        for token in tokens:
            with self.subTest(token=token):
                self.assert_ruby_contract(token + RUBY_PAGE, True)
                self.assert_ruby_contract(RUBY_PAGE.replace('Reviewed task choice', 'Reviewed' + token + ' task choice')
                                         .replace('Use ', 'Use' + token + ' ')
                                         .replace('<em>Fixture Code</em>', '<em>Fixture' + token + ' Code</em>'), True)
        # Native CDATA does not need an SGML ]]> close. Only the first > is
        # nonrendered; genuine reviewed text after it must remain usable.
        self.assert_ruby_contract(RUBY_PAGE.replace('Use ', '<![CDATA[>Use '), True)

    def test_native_declaration_and_comment_visible_suffixes_withdraw_affected_units(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        tokens = ('<![CDATA[>', '<![cdata[>', '<![CdAtA[>', '<![INCLUDE[>', '<![IGNORE[>',
                  '<![if unused]>', '<![unknown>', '<!unused "quoted>', '<?unused>',
                  '<!-->', '<!--->', '<!--unused--!>')
        for token in tokens:
            fragment = token + ' Only for preview accounts.]]>'
            for text in ('Reviewed task choice', ' for coding.', '<em>Fixture Code</em>'):
                with self.subTest(token=token, context=text):
                    self.assert_ruby_contract(RUBY_PAGE.replace(text, text + fragment), False)
        # Quotes do not extend a bogus comment/PI past the first >, and a
        # nested comment opener does not hide text after its actual close.
        for fragment in ('<!bogus "x>Only for preview accounts.">',
                         '<?bogus "x>Only for preview accounts."?>',
                         '<!--<!-->Only for preview accounts.-->',
                         '<!-->Only for preview accounts.<!-- ignored -->',
                         '<!--->Only for preview accounts.<!-- ignored -->'):
            with self.subTest(fragment=fragment):
                self.assert_ruby_contract(RUBY_PAGE.replace('</p>', fragment + '</p>'), False)

    def test_native_declaration_boundaries_preserve_hidden_excluded_leaf_link_and_adjacency_rules(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        qualifier = '<![CDATA[> Only for preview accounts.]]>'
        self.assert_ruby_contract(RUBY_PAGE.replace('</p>', '<span hidden>' + qualifier + '</span></p>'), True)
        for tag in ('del', 's', 'strike', 'q', 'blockquote'):
            with self.subTest(excluded=tag):
                self.assert_ruby_contract(RUBY_PAGE.replace('</p>', '<' + tag + '>' + qualifier + '</' + tag + '></p>'), False)
        self.assert_ruby_contract(RUBY_PAGE.replace('</h2>', '</h2><p>' + qualifier + '</p>'), False)
        self.assert_ruby_contract(RUBY_PAGE.replace('</p>', '<div>' + qualifier + '</div></p>'), False)
        link = '<a href="/api/docs/models/fixture-code"><em>Fixture Code</em></a>'
        self.assert_ruby_contract(RUBY_PAGE.replace(link, 'Fixture Code<!--' + link + '-->'), False)
        for tag in ('script', 'style', 'xmp', 'iframe', 'noembed', 'noframes', 'noscript', 'textarea', 'title', 'plaintext', 'template'):
            with self.subTest(scope=tag):
                self.assert_ruby_contract('<' + tag + '>' + qualifier + RUBY_PAGE + '</' + tag + '>', False)
                if tag != 'plaintext':
                    self.assert_ruby_contract('<' + tag + '>' + qualifier + 'unused</' + tag + '>' + RUBY_PAGE, True)

    def test_native_declaration_boundaries_preserve_pricing_discrimination(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(rate['input'], rate['output']) for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for token in ('<![CDATA[unused>', '<![cdata[unused>', '<![INCLUDE[unused>',
                      '<!unused>', '<?unused?>', '<!-- unused > -->'):
            with self.subTest(token=token):
                self.assertEqual(rates(token + sample.replace('Standard', 'Standard' + token)
                                       .replace('$0.75', token + '$0.75')), [(0.75, 4.5)])
        for token in ('<![CDATA[>', '<![cdata[>', '<![INCLUDE[>', '<!unused>', '<?unused>', '<!-->'):
            for text, qualifier in (('Standard', ' Batch'), ('Short context', ' Long context'),
                                    ('fixture-code', ' Only for preview accounts.'), ('$0.75', ' $90')):
                with self.subTest(token=token, context=text):
                    self.assertEqual(rates(sample.replace(text, text + token + qualifier + ']]>')), [])
        qualifier = '<![CDATA[> Batch]]>'
        self.assertEqual(rates(sample.replace('Standard', 'Standard<span hidden>' + qualifier + '</span>')), [(0.75, 4.5)])
        self.assertEqual(rates('<svg><![CDATA[></svg>' + sample + ']]></svg>'), [])
        self.assertEqual(rates('<template><svg><![CDATA[></template></svg>' + sample + ']]></svg></template>'), [])

    def test_deep_visible_wrappers_and_inline_text_confirm_fresh_acceptance(self):
        for depth in (1200, 2400):
            wrap = lambda text, tag: ('<' + tag + '>') * depth + text + ('</' + tag + '>') * depth
            for page in (wrap(RUBY_PAGE, 'div'),
                         RUBY_PAGE.replace('Reviewed task choice', wrap('Reviewed task choice', 'span'))
                                  .replace('<em>Fixture Code</em>', wrap('Fixture Code', 'span')),
                         RUBY_PAGE.replace('<p>', '<section>' + '<div>' * depth + '<p>')
                                  .replace('</p>', '</p>' + '</div>' * depth + '</section>')):
                with self.subTest(depth=depth, size=len(page)):
                    self.assert_ruby_contract(page, True)

    def test_deep_wrappers_preserve_visibility_leaf_order_and_link_refusals(self):
        depth = 1200
        wrap = lambda text: '<div>' * depth + text + '</div>' * depth
        link = '<a href="/api/docs/models/fixture-code"><em>Fixture Code</em></a>'
        pages = (wrap(RUBY_PAGE.replace('for coding.', 'for coding only in preview.')),
                 '<div hidden>' + wrap(RUBY_PAGE) + '</div>',
                 '<template>' + wrap(RUBY_PAGE) + '</template>',
                 '<blockquote>' + wrap(RUBY_PAGE) + '</blockquote>',
                 wrap(RUBY_PAGE.replace(link, '<span>Fixture Code</span><span hidden>' + link + '</span>')),
                 wrap(RUBY_PAGE.replace('<p>', '<div><p>').replace('</p>', '</p>Other qualifier</div>')),
                 wrap(RUBY_PAGE.replace('</h2>', '</h2>' + wrap(''))),
                 wrap(RUBY_PAGE.replace('for coding.', 'for <div>coding.</div>')),
                 '<div hidden><table>' + wrap(RUBY_PAGE) + '</div></table>',
                 RUBY_PAGE.replace(link, '<span>' * depth + link.replace('fixture-code', 'other') + '</span>' * depth),
                 RUBY_PAGE.replace('for coding.', '<span>' * depth + 'for coding only in preview.' + '</span>' * depth),
                 RUBY_PAGE.replace(link, '<span>' * depth + '<q>' + link + '</q>' + '</span>' * depth),
                 RUBY_PAGE.replace('for coding.', 'for ' + '<span>' * depth + '<div>coding.</div>' + '</span>' * depth))
        for index, page in enumerate(pages):
            with self.subTest(case=index):
                self.assert_ruby_contract(page, False)
        # Empty inline wrappers have no leaf-block or adjacency authority.
        self.assert_ruby_contract(RUBY_PAGE.replace('</h2>', '</h2>' + '<span>' * depth + '</span>' * depth), True)

    def test_deep_wrappers_preserve_pricing_and_visible_qualifiers(self):
        depth = 2400
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        wrap = lambda text, tag: ('<' + tag + '>') * depth + text + ('</' + tag + '>') * depth
        def rates(page):
            return [(rate['input'], rate['output']) for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        self.assertEqual(rates(wrap(sample, 'div')), [(0.75, 4.5)])
        self.assertEqual(rates(sample.replace('Standard', wrap('Standard', 'span'))), [(0.75, 4.5)])
        self.assertEqual(rates('<div hidden>' + wrap(sample, 'div') + '</div>'), [])
        self.assertEqual(rates(wrap(sample.replace('Standard', 'Standard Batch'), 'div')), [])
        self.assertEqual(rates(wrap(sample.replace('$0.75', '$90 $0.75'), 'div')), [])

    def test_legacy_image_hidden_cannot_erase_visible_text_successors(self):
        # The required model link is second; both clocks and a usable retained
        # proposal are pinned by assert_ruby_contract at all four public seams.
        self.assert_ruby_contract(RUBY_PAGE, True)
        page = RUBY_PAGE.replace('</p>', '<image hidden> Only if separately approved.</image></p>')
        self.assert_ruby_contract(page, False)

    def test_legacy_void_and_ignored_starts_cannot_hide_visible_successors(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        for tag in ('basefont', 'bgsound', 'frame'):
            with self.subTest(tag=tag):
                fragment = '<' + tag + ' hidden> Only if separately approved.</' + tag + '>'
                self.assert_ruby_contract(RUBY_PAGE.replace('</p>', fragment + '</p>'), False)
                self.assert_ruby_contract('<' + tag + ' hidden>' + RUBY_PAGE, True)

    def test_legacy_native_tokens_preserve_heading_paragraph_and_link_qualifiers(self):
        for tag in ('image', 'img', 'basefont', 'bgsound', 'frame', 'keygen'):
            for ending in ('>', '/>'):
                fragment = '<' + tag + ' HIDDEN="until-found"' + ending + ' only if approved</' + tag + '>'
                for text in ('Reviewed task choice', ' for coding.', '<em>Fixture Code</em>'):
                    with self.subTest(tag=tag, ending=ending, text=text):
                        self.assert_ruby_contract(RUBY_PAGE.replace(text, text + fragment), False)
        for token in ('<image>', '<IMAGE hidden="false"/>', '<image hidden hidden="false">',
                      '<basefont hidden/>', '<bgsound HIDDEN="">', '<frame hidden/>'):
            with self.subTest(token=token):
                self.assert_ruby_contract(token + RUBY_PAGE, True)
                self.assert_ruby_contract(RUBY_PAGE.replace('</p>', token + '</p>'), True)

    def test_legacy_tokens_preserve_actual_hidden_ancestors_and_containers(self):
        for opening, closing in (('<div hidden>', '</div>'), ('<span hidden>', '</span>'),
                                 ('<details>', '</details>'), ('<dialog>', '</dialog>')):
            with self.subTest(ancestor=opening):
                self.assert_ruby_contract(opening + '<image hidden>' + RUBY_PAGE + closing, False)
                self.assert_ruby_contract(opening + '<image hidden>unused' + closing + RUBY_PAGE, True)
        # Other obsolete or unknown names remain actual containers; voidness
        # is a bounded native rule, not a blanket legacy-name classification.
        for tag in ('isindex', 'image-box'):
            with self.subTest(container=tag):
                fragment = '<' + tag + ' hidden> only if approved</' + tag + '>'
                self.assert_ruby_contract(RUBY_PAGE.replace('</p>', fragment + '</p>'), True)
                self.assert_ruby_contract('<' + tag + ' hidden>' + RUBY_PAGE + '</' + tag + '>', False)
        self.assert_ruby_contract('<form><image hidden>' + RUBY_PAGE + '</form>', True)
        self.assert_ruby_contract('<head hidden><image hidden>' + RUBY_PAGE, True)
        self.assert_ruby_contract('<head hidden><frame hidden>' + RUBY_PAGE, True)

    def test_legacy_keygen_cannot_erase_visible_qualifiers(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        self.assert_ruby_contract(RUBY_PAGE.replace('</p>', '<keygen hidden> only if approved</keygen></p>'), False)
        self.assert_ruby_contract('<form><keygen hidden/>' + RUBY_PAGE + '</form>', True)
        self.assert_ruby_contract('<div hidden><keygen hidden>' + RUBY_PAGE + '</div>', False)
        for opening, closing in (('<svg>', '</svg>'), ('<svg><foreignObject>', '</foreignObject></svg>'),
                                 ('<template>', '</template>'), ('<textarea>', '</textarea>')):
            with self.subTest(scope=opening):
                self.assert_ruby_contract(opening + '<keygen hidden/>' + RUBY_PAGE + '</keygen>' + closing, False)
                self.assert_ruby_contract(opening + '<keygen hidden/>unused</keygen>' + closing + RUBY_PAGE, True)

    def test_legacy_image_keeps_foreign_integration_and_raw_inert_boundaries(self):
        scopes = (('<svg>', '</svg>'), ('<svg><foreignObject>', '</foreignObject></svg>'),
                  ('<svg><desc>', '</desc></svg>'), ('<svg><title>', '</title></svg>'),
                  ('<math>', '</math>'), ('<math><mtext>', '</mtext></math>'),
                  ('<math><annotation-xml encoding="text/html">', '</annotation-xml></math>'),
                  ('<select>', '</select>'), ('<frameset>', '</frameset>'),
                  ('<template>', '</template>'), ('<script>', '</script>'),
                  ('<textarea>', '</textarea>'), ('<noscript>', '</noscript>'))
        for opening, closing in scopes:
            with self.subTest(scope=opening):
                self.assert_ruby_contract(opening + '<image hidden>' + RUBY_PAGE + '</image>' + closing, False)
                self.assert_ruby_contract(opening + '<image hidden/>unused</image>' + closing + RUBY_PAGE, True)
        for fragment in ('<svg><image hidden/></svg>',
                         '<svg><foreignObject><image hidden/>unused</foreignObject></svg>',
                         '<math><mtext><image hidden/>unused</mtext></math>'):
            with self.subTest(fragment=fragment):
                # An inline foreign subtree stays ambiguous, even after a
                # genuine close; it cannot erase a qualifier in a reviewed unit.
                self.assert_ruby_contract(RUBY_PAGE.replace('</p>', fragment + ' only if approved</p>'), False)
        self.assert_ruby_contract('<svg><foreignObject><image hidden/></svg>' + RUBY_PAGE
                                 + '</image></foreignObject></svg>', False)
        self.assert_ruby_contract('<svg><image hidden><div hidden></image>' + RUBY_PAGE + '</div></svg>', False)

    def test_legacy_void_and_ignored_tokens_preserve_pricing_qualifiers(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(rate['input'], rate['output'])
                    for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for tag in ('image', 'img', 'basefont', 'bgsound', 'frame', 'keygen'):
            with self.subTest(tag=tag):
                self.assertEqual(rates('<' + tag + ' hidden>' + sample), [(0.75, 4.5)])
                self.assertEqual(rates(sample.replace('Standard', 'Standard<' + tag + ' hidden>Batch</' + tag + '>')), [])
                self.assertEqual(rates(sample.replace('$0.75', '<' + tag + ' hidden>$90</' + tag + '>$0.75')), [])
        self.assertEqual(rates(sample.replace('Standard', 'Standard<span hidden><image hidden>Batch</span>')),
                         [(0.75, 4.5)])
        self.assertEqual(rates('<div hidden><image hidden>' + sample + '</div>'), [])
        self.assertEqual(rates('<svg><image hidden>' + sample + '</image></svg>'), [])
        self.assertEqual(rates('<svg><foreignObject><image hidden/>' + sample + '</foreignObject></svg>'), [])

    def test_ruby_hidden_annotation_preserves_second_required_link(self):
        self.assert_ruby_contract(RUBY_PAGE, True)
        self.assert_ruby_contract(RUBY_PAGE.replace('<em>Fixture Code</em>',
                                                  '<ruby>Fixture Code<rt hidden>annotation</rt></ruby>'), True)

    def test_ruby_implied_annotation_ends_preserve_visibility(self):
        cases = (('<ruby><rb hidden>unused<rb>Fixture Code</ruby>', True),
                 ('<ruby><rt hidden>annotation<rp hidden>(<rt hidden/>annotation<rb>Fixture Code</ruby>', True),
                 ('<ruby><rtc hidden><rt>annotation<rt>more<rb>Fixture Code</ruby>', True),
                 ('<ruby><rtc hidden>annotation<rtc>Fixture Code</ruby>', True),
                 ('<ruby>Fixture Code<rt hidden>annotation<rt> only when approved</ruby>', False),
                 ('<ruby>Fixture Code<rp hidden>(<rp> only when approved</ruby>', False),
                 ('<ruby><rtc hidden><rt>unused<rt>Fixture Code</ruby>', False),
                 ('<ruby><rt hidden><span>unused<rt>Fixture Code</rt></span></ruby>', False),
                 ('<span hidden><rt>unused<rt>Fixture Code</span>', False),
                 ('<ruby><table><tr><td hidden><rt>unused<rt>Fixture Code</td></tr></table></ruby>', False),
                 ('<ruby hidden><rt>unused<rb>Fixture Code</ruby>', False),
                 ('<ruby>Fixture Code<rt hidden><ruby><rt>unused</ruby></rt></ruby>', True))
        for label, confirmed in cases:
            with self.subTest(label=label):
                self.assert_ruby_contract(RUBY_PAGE.replace('<em>Fixture Code</em>', label), confirmed)

    def test_ruby_phrasing_heading_paragraph_and_link_context(self):
        for tag in ('ruby', 'rb', 'rp', 'rt', 'rtc'):
            with self.subTest(tag=tag):
                # Visible annotation text is retained, not discarded by tag name.
                label = '<ruby><' + tag + '>Fixture Code</' + tag + '><rt hidden>unused</rt></ruby>'
                self.assert_ruby_contract(RUBY_PAGE.replace('<em>Fixture Code</em>', label), True)
                self.assert_ruby_contract(RUBY_PAGE.replace('Reviewed task choice',
                    '<ruby><' + tag + '>Reviewed task choice</' + tag + '><rt hidden>unused</rt></ruby>'), True)
                self.assert_ruby_contract(RUBY_PAGE.replace('Compare ',
                    '<ruby><' + tag + '>Compare </' + tag + '><rt hidden>unused</rt></ruby>'), True)
                self.assert_ruby_contract(RUBY_PAGE.replace('<em>Fixture Code</em>',
                    '<ruby>Fixture Code<' + tag + '> only when approved</' + tag + '></ruby>'), False)
        for tag in ('em', 'span', 'bdi', 'data', 'code'):
            with self.subTest(descendant=tag):
                label = '<ruby><' + tag + '>Fixture Code</' + tag + '><rt hidden><' + tag + '>unused</' + tag + '></rt></ruby>'
                self.assert_ruby_contract(RUBY_PAGE.replace('<em>Fixture Code</em>', label), True)

    def test_ruby_cannot_bypass_hidden_excluded_or_structural_context(self):
        label = '<ruby>Fixture Code<rt hidden>annotation</rt></ruby>'
        page = RUBY_PAGE.replace('<em>Fixture Code</em>', label)
        for opening, closing in (('<span hidden>', '</span>'), ('<ruby hidden/>', '</ruby>'),
                                 ('<template>', '</template>'), ('<script>', '</script>'),
                                 ('<select hidden>', '</select>'), ('<svg>', '</svg>'),
                                 ('<blockquote>', '</blockquote>')):
            with self.subTest(ancestor=opening):
                self.assert_ruby_contract(opening + page + closing, False)
                self.assert_ruby_contract(opening + '<ruby><rt hidden>unused</rt></ruby>' + closing + RUBY_PAGE, True)
        for fragment in ('<ruby><div>Fixture Code</div></ruby>',
                         '<ruby><p hidden>unused</p>Fixture Code</ruby>',
                         '<ruby><rt hidden><div>unused</div></rt>Fixture Code</ruby>',
                         '<ruby><b hidden>unused</ruby>Fixture Code',
                         '<ruby><q>Fixture Code</q></ruby>',
                         'Fixture Code<template><ruby><a href="/api/docs/models/fixture-code">unused</a></ruby></template>'):
            with self.subTest(fragment=fragment):
                changed = page.replace(label, fragment)
                if fragment.startswith('Fixture Code<template>'):
                    changed = changed.replace('<a href="/api/docs/models/fixture-code">' + fragment + '</a>', fragment)
                self.assert_ruby_contract(changed, False)
        self.assert_ruby_contract(page.replace('<a href="/api/docs/models/fixture-code">',
                                              '<a hidden href="/api/docs/models/fixture-code">'), False)

    def test_ruby_pricing_preserves_hidden_annotations_and_visible_qualifiers(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(rate['input'], rate['output'])
                    for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        self.assertEqual(rates(sample.replace('Standard', '<ruby>Standard<rt hidden>Batch</rt></ruby>')),
                         [(0.75, 4.5)])
        self.assertEqual(rates(sample.replace('Standard', '<ruby>Standard<rt hidden>unused<rt> Batch</ruby>')), [])
        self.assertEqual(rates(sample.replace('$0.75', '<ruby><rt hidden>unused<rb>$0.75</ruby>')),
                         [(0.75, 4.5)])
        self.assertEqual(rates(sample.replace('$0.75', '<ruby hidden>$0.75<rt>unused</rt></ruby>')), [])

    def test_hidden_ancestor_table_scope_ignores_unrelated_close(self):
        entry = {**ENTRY, 'heading': 'Reviewed coding choice',
                 'paragraph': 'Compare Other Model first. Use Fixture Code for coding.'}
        page = ('<h2>Reviewed coding choice</h2><p>Compare <a href="/api/docs/models/other">Other Model</a> first. '
                'Use <a href="/api/docs/models/fixture-code"><em>Fixture Code</em></a> for coding.</p>')
        with patch.object(fixtures, 'NOW', '2026-10-06T00:00:00Z'):
            self.assert_fresh_page_contract(page, True, baseline=page, entry=entry)
            for opening in ('<table>', '<table/>'):
                self.assert_fresh_page_contract('<div hidden>' + opening + '</div>' + page + '</table></div>', False,
                                                baseline=page, entry=entry)
            self.assert_fresh_page_contract('<div hidden><table></table></div>' + page, True,
                                            baseline=page, entry=entry)

    def test_native_table_scope_families_and_closed_successors(self):
        self.assert_fresh_page_contract(PAGE, True)
        layouts = (('<table>', '</table>'), ('<table><thead>', '</thead></table>'),
                   ('<table><tbody>', '</tbody></table>'), ('<table><tfoot>', '</tfoot></table>'),
                   ('<table><tr>', '</tr></table>'), ('<table><tr><td>', '</td></tr></table>'),
                   ('<table><tr><th>', '</th></tr></table>'), ('<table><caption>', '</caption></table>'),
                   ('<table><colgroup>', '</colgroup></table>'))
        for opening, closing in layouts:
            with self.subTest(layout=opening):
                self.assert_fresh_page_contract('<div hidden>' + opening + '</div>' + PAGE + closing + '</div>', False)
                self.assert_fresh_page_contract('<div hidden>' + opening + closing + '</div>' + PAGE, True)
        for ancestor, opening, closing in (('li', '<ul><li hidden>', '</li></ul>'),
                                            ('dd', '<dl><dd hidden>', '</dd></dl>'),
                                            ('section', '<section hidden>', '</section>')):
            with self.subTest(ancestor=ancestor):
                self.assert_fresh_page_contract(opening + '<table></' + ancestor + '>' + PAGE + '</table>' + closing, False)
                self.assert_fresh_page_contract(opening + '<table></table>' + closing + PAGE, True)

    def test_native_table_implied_and_explicit_ends_release_visible_successors(self):
        for prefix in ('<table><tr><td hidden>unused</tr></table>',
                       '<table><tbody><tr><th hidden>unused</tbody></table>',
                       '<table><tr><td><b hidden>unused</table>',
                       '<table><caption><em hidden>unused</table>'):
            with self.subTest(prefix=prefix):
                self.assert_fresh_page_contract(prefix + PAGE, True)
        for page in ('<table><caption hidden>unused<tr><td>' + PAGE + '</td></tr></table>',
                     '<table><colgroup hidden><col><tr><td>' + PAGE + '</td></tr></table>',
                     '<table><tr><td hidden>unused</tr><tr><td>' + PAGE + '</td></tr></table>',
                     '<table><tbody><tr><td hidden>unused</tbody><tbody><tr><td>' + PAGE + '</td></tr></tbody></table>',
                     '<table><caption hidden>unused<caption>' + PAGE + '</caption></table>'):
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, True)

    def test_generic_end_scopes_and_native_boundaries_cannot_release_hidden_ancestors(self):
        self.assert_fresh_page_contract(PAGE, True)
        for boundary in ('div', 'p', 'ul', 'ol', 'dl', 'fieldset', 'details'):
            with self.subTest(boundary=boundary):
                self.assert_fresh_page_contract('<span hidden><' + boundary + '></span>' + PAGE + '</' + boundary + '></span>', False)
                self.assert_fresh_page_contract('<span hidden><' + boundary + '>unused</' + boundary + '></span>' + PAGE, True)
        for boundary in ('button', 'object', 'applet', 'marquee', 'template', 'select', 'svg', 'math'):
            with self.subTest(boundary=boundary):
                self.assert_fresh_page_contract('<div hidden><' + boundary + '></div>' + PAGE + '</' + boundary + '></div>', False)
                self.assert_fresh_page_contract('<div hidden><' + boundary + '>unused</' + boundary + '></div>' + PAGE, True)
        self.assert_fresh_page_contract('<div hidden><section>unused</div>' + PAGE, True)
        self.assert_fresh_page_contract('<form hidden><div></form>' + PAGE + '</div>', False)
        self.assert_fresh_page_contract('<form hidden><div>unused</div></form>' + PAGE, True)
        for tag in ('html', 'body'):
            self.assert_fresh_page_contract('<' + tag + ' hidden></' + tag + '>' + PAGE, False)

    def test_native_end_scopes_preserve_pricing_qualifiers_and_visible_tables(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(rate['input'], rate['output']) for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for prefix in ('<div hidden><table></div>', '<span hidden><div></span>', '<form hidden><div></form>'):
            with self.subTest(prefix=prefix):
                self.assertEqual(rates(prefix + sample), [])
        for prefix in ('<div hidden><table></table></div>', '<span hidden><div></div></span>',
                       '<table><tr><td><b hidden>unused</table>'):
            with self.subTest(prefix=prefix, closed=True):
                self.assertEqual(rates(prefix + sample), [(0.75, 4.5)])
        for fragment in ('<span hidden><span>unused</span></span> Batch',
                         '<div hidden><table></div></table></div> Batch'):
            with self.subTest(fragment=fragment):
                self.assertEqual(rates(sample.replace('Standard', 'Standard' + fragment)), [])
        self.assertEqual(rates(sample.replace('Standard', 'Standard<span hidden>Batch</span>')), [(0.75, 4.5)])

    def test_table_scope_refusal_preserves_adopted_project_and_recovered_proposals(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache, log = Path(temporary) / 'cache', Path(temporary) / 'fetches'
            pages, fetched = {SOURCES[0]: PAGE}, []
            def fetch(url):
                fetched.append(url)
                return pages.get(url, '<p>Unknown</p>')
            official = OfficialSources(lambda: fixtures.NOW, fetch=fetch, reviewed=[ENTRY])
            service = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                    recommendation_sources=official.retrieve, evidence_dir=Path(temporary) / 'service')
            draft = service.read()
            (self.project / '.playbook-config.json').write_text(json.dumps(
                {'schema_version': 1, 'adopted': True, 'models': draft['before']}))
            (self.project / 'approved.json').write_bytes(b'{"approved": "keep"}\n')
            draft = service.read()
            cli_draft = self.official_cli('read', {'context': self.context}, cache, pages=pages, reviewed=[ENTRY])
            recovery = self.official_cli('reply', {'proposal': cli_draft}, cache, expected_code=2, pages=pages, reviewed=[ENTRY])
            retained = recovery['retained_proposal']
            for proposal in (draft, cli_draft, retained):
                self.assertIn('Accept replacement', proposal['choices'])
            project_bytes = {path.name: path.read_bytes() for path in self.project.iterdir()}
            proposal_bytes = [json.dumps(proposal, sort_keys=True).encode() for proposal in (draft, cli_draft, recovery)]
            pages[SOURCES[0]] = '<div hidden><table></div>' + PAGE + '</table></div>'
            for fail_cache_write in (False, True):
                fetched.clear()
                cache_patch = patch('model_evidence_cache.os.replace', side_effect=OSError('Controlled persistence failure')) if fail_cache_write else nullcontext()
                with cache_patch:
                    result = service.reply(draft, 'Accept replacement')
                self.assertEqual(fetched, [SOURCES[0]])
                results = [(draft, result)]
                for proposal in (cli_draft, retained):
                    log.write_text('')
                    result = self.official_cli('reply', {'proposal': proposal, 'reply': 'Accept replacement'}, cache,
                                               pages=pages, reviewed=[ENTRY], fail_cache_write=fail_cache_write, fetch_log=log)
                    self.assertEqual(log.read_text().splitlines(), [SOURCES[0]])
                    results.append((proposal, result))
                for proposal, result in results:
                    self.assertEqual(result['after'], proposal['after'])
                    self.assertNotIn('Accept replacement', result['choices'])
                    self.assertIsNone(result['recommendations'][proposal['replacement']['role']]['choice'])
                    self.assertIn(WITHDRAWN, result['message'])
                    self.assertFalse(result['launched'])
                self.assertEqual({path.name: path.read_bytes() for path in self.project.iterdir()}, project_bytes)
                self.assertEqual([json.dumps(proposal, sort_keys=True).encode() for proposal in (draft, cli_draft, recovery)], proposal_bytes)

    def test_hidden_active_formatting_survives_paragraph_close(self):
        self.assert_fresh_page_contract(PAGE, True)
        self.assert_fresh_page_contract('<p><b hidden>unused</p>' + PAGE, False)

    def test_formatting_adoption_and_markers_keep_visibility_bounded(self):
        self.assert_fresh_page_contract(PAGE, True)
        for page in ('<p><b hidden>unused</p><b>unused</b>' + PAGE,
                     PAGE.replace('</h2>', '<a hidden><a></a> only for unreviewed work</a></h2>'),
                     PAGE.replace('</h2>', '<nobr hidden><nobr></nobr> only for unreviewed work</nobr></h2>')):
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, False)
        self.assert_fresh_page_contract('<table><tr><td><b hidden>unused</td></tr></table>' + PAGE, True)

    def test_active_formatting_families_structural_ends_and_closed_successors(self):
        families = ('a', 'b', 'big', 'code', 'em', 'font', 'i', 'nobr', 's', 'small', 'strike', 'strong', 'tt', 'u')
        self.assertTrue(self.retrieve(PAGE)['guidance'])
        for tag in families:
            for attribute in ('hidden', 'HiDdEn="until-found"', 'hidden="false"'):
                for ending in ('>', '/>'):
                    opening = '<' + tag + ' ' + attribute + ending
                    close = '</' + tag + '>'
                    for prefix in ('<p>' + opening + 'unused</p>', '<p>' + opening + 'unused',
                                   '<div>' + opening + 'unused</div>', '<h3>' + opening + 'unused</h3>',
                                   '<ul><li>' + opening + 'unused<li>visible</li></ul>'):
                        with self.subTest(tag=tag, attribute=attribute, ending=ending, prefix=prefix):
                            self.assertFalse(self.retrieve(prefix + PAGE)['guidance'])
                    for prefix in ('<p>' + opening + 'unused' + close + '</p>',
                                   '<p>' + opening + 'unused</p>' + close):
                        with self.subTest(tag=tag, prefix=prefix):
                            self.assertTrue(self.retrieve(prefix + PAGE)['guidance'])
                    for insertion in ('</h2>', '</p>'):
                        with self.subTest(tag=tag, insertion=insertion):
                            # Hidden formatting supplies no text, but s/strike
                            # still violate the separate structural exclusion.
                            self.assertEqual(bool(self.retrieve(PAGE.replace(insertion, opening + 'unused' + close + insertion))['guidance']),
                                             tag not in {'s', 'strike'})
            for ancestor, close in (('<div hidden>', '</div>'), ('<dialog>', '</dialog>'),
                                    ('<details>', '</details>'), ('<datalist>', '</datalist>')):
                prefix = ancestor + '<' + tag + '>unused' + close
                with self.subTest(tag=tag, ancestor=ancestor):
                    self.assertFalse(self.retrieve(prefix + PAGE)['guidance'])
                    self.assertTrue(self.retrieve(prefix + '</' + tag + '>' + PAGE)['guidance'])
            for wrapper in ('template', 'script', 'textarea', 'select', 'button', 'svg', 'math'):
                with self.subTest(tag=tag, excluded=wrapper):
                    self.assertTrue(self.retrieve('<' + wrapper + '><p><' + tag + ' hidden>unused</p></' + wrapper + '>' + PAGE)['guidance'])
            for cell in ('td', 'th', 'caption'):
                prefix = '<table>' + ('<tr>' if cell != 'caption' else '') + '<' + cell + '><' + tag + ' hidden>unused</' + cell + '>'
                prefix += '</tr></table>' if cell != 'caption' else '</table>'
                with self.subTest(tag=tag, marker=cell):
                    self.assertTrue(self.retrieve(prefix + PAGE)['guidance'])
            if tag not in ('s', 'strike'):
                with self.subTest(tag=tag, visible=True):
                    self.assertTrue(self.retrieve(PAGE.replace(HEADING, '<' + tag + '>' + HEADING + '</' + tag + '>'))['guidance'])

    def test_formatting_reconstruction_inherited_and_misnested_fresh_acceptance(self):
        self.assert_fresh_page_contract(PAGE, True)
        for prefix in ('<div hidden><em>unused</div>', '<dialog><font>unused</dialog>',
                       '<details><code>unused</details>', '<p><b><i hidden>unused</b></p>',
                       '<ul><li><strong hidden/>unused<li>visible</li></ul>',
                       '<p><a hidden href="/unused">unused</p>'):
            with self.subTest(prefix=prefix):
                self.assert_fresh_page_contract(prefix + PAGE, False)
        self.assert_fresh_page_contract('<p><b hidden>unused</p></b><form>' + PAGE + '</form>', True)
        self.assert_fresh_page_contract('<template><p><b hidden>unused</p></template>' + PAGE, True)

    def test_native_formatting_markers_release_closed_visible_successors(self):
        self.assert_fresh_page_contract('<marquee><b hidden>unused</marquee>' + PAGE, True)
        for tag in ('button', 'object', 'applet'):
            with self.subTest(tag=tag):
                self.assertTrue(self.retrieve('<' + tag + '><b hidden>unused</' + tag + '>' + PAGE)['guidance'])
        self.assertTrue(self.retrieve('<table><tr><td><b hidden>unused<td>visible</td></tr></table>' + PAGE)['guidance'])
        # A formatting close inside a cell cannot remove an entry before its marker.
        self.assertFalse(self.retrieve('<p><b hidden>unused</p><table><tr><td></b></td></tr></table>' + PAGE)['guidance'])

    def test_formatting_own_closes_release_visible_units_inside_layouts(self):
        for page in ('<p><b hidden>unused</p><main><div></b>' + PAGE + '</div></main>',
                     '<p><b hidden>unused</p><main><span>unused</span></b>' + PAGE + '</main>',
                     '<p><b hidden>unused</p><main><h2></b>' + HEADING + '</h2><p>' + LINKED + '</p></main>'):
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, True)

    def test_adoption_across_open_blocks_cannot_prove_later_visibility(self):
        self.assert_fresh_page_contract(PAGE, True)
        # Adoption can clone formatting around a furthest block. Repeated
        # closes are not proof that a bounded visibility stack released it.
        for tag in ('a', 'b', 'code', 'em', 'font', 'i', 'strong'):
            for depth in (1, 9, 17):
                prefix = '<' + tag + ' hidden>' + '<div>' * depth + 'unused</' + tag + '>'
                with self.subTest(tag=tag, depth=depth):
                    self.assertFalse(self.retrieve(prefix + PAGE + '</div>' * depth)['guidance'])
                    self.assertFalse(self.retrieve(prefix + '</' + tag + '>' + PAGE + '</div>' * depth)['guidance'])
                    closed = '<' + tag + ' hidden>' + '<div>' * depth + 'unused' + '</div>' * depth + '</' + tag + '>'
                    self.assertTrue(self.retrieve(closed + PAGE)['guidance'])
        self.assert_fresh_page_contract('<b hidden>' + '<div>' * 9 + 'unused</b>' + PAGE + '</div>' * 9, False)
        self.assert_fresh_page_contract('<table><tr><td><b hidden><div>unused</b></div></td></tr></table>' + PAGE, True)

    def test_active_formatting_pricing_keeps_qualifiers_and_closed_positives(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(rate['input'], rate['output']) for rate in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for prefix in ('<p><b hidden>unused</p>', '<div hidden><em>unused</div>', '<b><i hidden>unused</b>'):
            with self.subTest(prefix=prefix):
                self.assertEqual(rates(prefix + sample), [])
        for tag in ('a', 'nobr'):
            fragment = '<' + tag + ' hidden><' + tag + '></' + tag + '>Batch</' + tag + '>'
            with self.subTest(tag=tag, context='tier'):
                self.assertEqual(rates(sample.replace('Standard', 'Standard' + fragment)), [])
            with self.subTest(tag=tag, context='rate'):
                self.assertEqual(rates(sample.replace('$0.75', '$0.75' + fragment.replace('Batch', '90'))), [])
        for prefix in ('<p><b hidden>unused</b></p>', '<p><b hidden>unused</p></b>',
                       '<table><tr><td><b hidden>unused</td></tr></table>',
                       '<script><b hidden>unused</script>', '<template><b hidden>unused</template>'):
            with self.subTest(prefix=prefix, closed=True):
                self.assertEqual(rates(prefix + sample), [(0.75, 4.5)])
        self.assertEqual(rates(sample.replace('Standard', 'Standard<b hidden>Batch</b>')), [(0.75, 4.5)])

    def test_formatting_refusal_preserves_adopted_project_and_retained_proposals(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache, log = Path(temporary) / 'cache', Path(temporary) / 'fetches'
            pages, fetched = {SOURCES[0]: PAGE}, []
            def fetch(url):
                fetched.append(url)
                return pages.get(url, '<p>Unknown</p>')
            official = OfficialSources(lambda: fixtures.NOW, fetch=fetch, reviewed=[ENTRY])
            service = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                    recommendation_sources=official.retrieve, evidence_dir=Path(temporary) / 'service')
            draft = service.read()
            (self.project / '.playbook-config.json').write_text(json.dumps(
                {'schema_version': 1, 'adopted': True, 'models': draft['before']}))
            (self.project / 'approved.json').write_bytes(b'{"approved": "keep"}\n')
            draft = service.read()
            cli_draft = self.official_cli('read', {'context': self.context}, cache, pages=pages, reviewed=[ENTRY])
            recovery = self.official_cli('reply', {'proposal': cli_draft}, cache, expected_code=2,
                                         pages=pages, reviewed=[ENTRY])
            for proposal in (draft, cli_draft, recovery['retained_proposal']):
                self.assertIn('Accept replacement', proposal['choices'])
                self.assertIsNotNone(proposal['recommendations'][proposal['replacement']['role']]['choice'])
            project_bytes = {path.name: path.read_bytes() for path in self.project.iterdir()}
            proposal_bytes = [json.dumps(proposal, sort_keys=True).encode() for proposal in (draft, cli_draft, recovery)]
            pages[SOURCES[0]] = '<p><b hidden>unused</p>' + PAGE
            for fail_cache_write in (False, True):
                fetched.clear()
                cache_patch = patch('model_evidence_cache.os.replace', side_effect=OSError('Controlled persistence failure')) if fail_cache_write else nullcontext()
                with cache_patch:
                    result = service.reply(draft, 'Accept replacement')
                self.assertEqual(fetched, [SOURCES[0]])
                results = [(draft, result)]
                for retained in (cli_draft, recovery['retained_proposal']):
                    log.write_text('')
                    result = self.official_cli('reply', {'proposal': retained, 'reply': 'Accept replacement'}, cache,
                                               pages=pages, reviewed=[ENTRY], fail_cache_write=fail_cache_write, fetch_log=log)
                    self.assertEqual(log.read_text().splitlines(), [SOURCES[0]])
                    results.append((retained, result))
                for proposal, result in results:
                    self.assertEqual(result['after'], proposal['after'])
                    self.assertNotIn('Accept replacement', result['choices'])
                    self.assertIsNone(result['recommendations'][proposal['replacement']['role']]['choice'])
                    self.assertIn(WITHDRAWN, result['message'])
                    self.assertFalse(result['launched'])
                self.assertEqual({path.name: path.read_bytes() for path in self.project.iterdir()}, project_bytes)
                self.assertEqual([json.dumps(proposal, sort_keys=True).encode() for proposal in (draft, cli_draft, recovery)], proposal_bytes)

    def test_select_option_markup_cannot_authorize_fresh_acceptance(self):
        self.assert_fresh_page_contract(PAGE, True)
        self.assert_fresh_page_contract('<select><option>' + PAGE + '</option></select>', False)

    def test_hidden_nested_select_cannot_erase_a_visible_heading_qualifier(self):
        self.assert_fresh_page_contract(PAGE, True)
        page = PAGE.replace('</h2>', '<select hidden><select></select> only for unreviewed work</select></h2>')
        self.assert_fresh_page_contract(page, False)

    def test_hidden_native_boundaries_cannot_erase_qualifiers_in_reviewed_units(self):
        self.assert_fresh_page_contract(PAGE, True)
        fragments = ('<button hidden><button></button> only for unreviewed work</button>',
                     '<select hidden><input> only for unreviewed work</select>',
                     '<select hidden><textarea></textarea> only for unreviewed work</select>',
                     '<option hidden><option></option> only for unreviewed work</option>',
                     '<optgroup hidden><optgroup></optgroup> only for unreviewed work</optgroup>',
                     '<frameset hidden> only for unreviewed work</frameset>',
                     '<svg hidden><p> only for unreviewed work</p></svg>',
                     '<math hidden><p> only for unreviewed work</p></math>',
                     '<span hidden><select><select></select></span> only for unreviewed work</select>')
        for fragment in fragments:
            for boundary in ('</h2>', ', our flagship', '</a>'):
                with self.subTest(fragment=fragment, boundary=boundary):
                    page = PAGE.replace(boundary, fragment + boundary, 1)
                    self.assert_fresh_page_contract(page, False)

    def test_hidden_content_models_keep_a_barrier_but_closed_successors_remain_usable(self):
        self.assert_fresh_page_contract(PAGE, True)
        for tag in ('select', 'option', 'optgroup', 'button', 'meter', 'progress', 'object', 'applet',
                    'audio', 'video', 'canvas', 'frameset', 'svg', 'math'):
            for attribute in ('hidden', 'HIDDEN="until-found"'):
                with self.subTest(tag=tag, attribute=attribute):
                    fragment = '<' + tag + ' ' + attribute + '>unused</' + tag + '>'
                    self.assertEqual(self.retrieve(PAGE.replace('</h2>', fragment + '</h2>'))['guidance'], [])
                    self.assertTrue(self.retrieve(fragment + PAGE)['guidance'])
                    self.assertTrue(self.retrieve('<div hidden>' + fragment + '</div>' + PAGE)['guidance'])
        self.assert_fresh_page_contract('<select hidden><select></select>unused</select>' + PAGE, True)
        self.assert_fresh_page_contract('<button hidden><button></button>unused</button>' + PAGE, True)

    def test_hidden_ignored_table_tokens_cannot_erase_visible_qualifiers(self):
        self.assert_fresh_page_contract(PAGE, True)
        # Without a table these starts are ignored by HTML. The span close
        # still exposes the qualifier; it cannot be withheld as table content.
        for tag in ('caption', 'colgroup', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th'):
            fragment = '<span hidden><' + tag + '></span> ONLY FOR UNREVIEWED WORK</' + tag + '>'
            for boundary in ('</h2>', ', our flagship', '</a>'):
                with self.subTest(tag=tag, boundary=boundary):
                    self.assert_fresh_page_contract(PAGE.replace(boundary, fragment + boundary, 1), False)

    def test_hidden_nested_forms_and_document_tokens_keep_ambiguity_barriers(self):
        self.assert_fresh_page_contract('<form>' + PAGE + '</form>', True)
        document = '<html><head><title>Models</title></head><body>' + PAGE + '</body></html>'
        self.assert_fresh_page_contract(document, True)
        for tag in ('form', 'html', 'head', 'body'):
            original = '<form>' + PAGE + '</form>' if tag == 'form' else document
            fragment = '<span hidden><' + tag + '></span> ONLY FOR UNREVIEWED WORK</' + tag + '>'
            for boundary in ('</h2>', ', our flagship', '</a>'):
                with self.subTest(tag=tag, boundary=boundary):
                    self.assert_fresh_page_contract(original.replace(boundary, fragment + boundary, 1), False)

    def test_ignored_scope_nesting_closes_and_self_closing_flags_preserve_barriers(self):
        self.assert_fresh_page_contract(PAGE, True)
        for tag in ('tr', 'form', 'head'):
            original = '<form>' + PAGE + '</form>' if tag == 'form' else PAGE
            for fragment in ('<span hidden><' + tag + '/></span> ONLY FOR UNREVIEWED WORK</' + tag + '>',
                             '<span HIDDEN="until-found"><' + tag + '><' + tag + '></span>'
                             ' ONLY FOR UNREVIEWED WORK</' + tag + '></' + tag + '>',
                             '<dialog><' + tag + '></dialog> ONLY FOR UNREVIEWED WORK</' + tag + '>',
                             '<details><' + tag + '></details> ONLY FOR UNREVIEWED WORK</' + tag + '>'):
                with self.subTest(tag=tag, fragment=fragment):
                    self.assert_fresh_page_contract(original.replace('</h2>', fragment + '</h2>', 1), False)

    def test_ignored_scope_barriers_preserve_valid_successors_and_inert_exclusions(self):
        for tag in ('caption', 'colgroup', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'head', 'form'):
            original = '<form>' + PAGE + '</form>' if tag == 'form' else PAGE
            prefix = '<span hidden><' + tag + '>unused</' + tag + '></span>'
            with self.subTest(tag=tag):
                self.assert_fresh_page_contract(original.replace('<main>', prefix + '<main>', 1), True)
        fragment = '<span hidden><tr></span> ONLY FOR UNREVIEWED WORK</tr>'
        for tag in ('template', 'script', 'style', 'textarea'):
            with self.subTest(tag=tag):
                self.assert_fresh_page_contract(PAGE.replace('</h2>', '<' + tag + '>' + fragment + '</' + tag + '></h2>'), True)
        self.assert_fresh_page_contract(PAGE.replace('</h2>', '<span hidden>ONLY FOR UNREVIEWED WORK</span></h2>'), True)

    def test_hidden_ignored_scope_pricing_barriers_preserve_tier_and_rate_qualifiers(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(record['input'], record['output']) for record in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for tag in ('caption', 'colgroup', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'form', 'html', 'head', 'body'):
            original = '<form>' + sample + '</form>' if tag == 'form' else sample
            for ancestor, close in (('<span hidden>', '</span>'), ('<dialog>', '</dialog>'), ('<details>', '</details>')):
                fragment = ancestor + '<' + tag + '>' + close + 'Batch</' + tag + '>'
                with self.subTest(tag=tag, ancestor=ancestor):
                    self.assertEqual(rates(original.replace('Standard', 'Standard' + fragment)), [])
        # In a table cell tr/td/th are structural rather than ignored. Use
        # ignored nested form/head tokens here and retain the cell boundaries.
        for tag in ('form', 'head'):
            original = '<form>' + sample + '</form>' if tag == 'form' else sample
            fragment = '<span hidden><' + tag + '></span>90</' + tag + '>'
            with self.subTest(tag=tag, boundary='rate'):
                self.assertEqual(rates(original.replace('$0.75', '$' + fragment + '0.75')), [])
        self.assertEqual(rates(sample.replace('Standard', 'Standard<span hidden>Batch</span>')), [(0.75, 4.5)])
        self.assertEqual(rates('<span hidden><tr>unused</tr></span>' + sample), [(0.75, 4.5)])

    def test_hidden_native_pricing_boundaries_cannot_erase_tier_or_rate_qualifiers(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(record['input'], record['output']) for record in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for tag in ('select', 'button', 'frameset', 'svg', 'math'):
            with self.subTest(tag=tag):
                fragment = '<' + tag + ' hidden><' + tag + '></' + tag + '>Batch</' + tag + '>'
                self.assertEqual(rates(sample.replace('Standard', 'Standard' + fragment)), [])
                self.assertEqual(rates(sample.replace('$0.75', '$' + fragment + '0.75')), [])
                self.assertEqual(rates(fragment + sample), [(0.75, 4.5)])
        self.assertEqual(rates(sample.replace('Standard', 'Standard<span hidden>Batch</span>')), [(0.75, 4.5)])

    def test_select_scopes_withhold_nested_malformed_and_implicit_close_copies(self):
        pages = ('<select>' + PAGE + '</select>',
                 '<select><optgroup><option>' + PAGE + '</select>',
                 '<select/><option/>' + PAGE + '</option></select>',
                 '<select><option>Unused<option>' + PAGE + '</select>',
                 '<select><optgroup>Unused<optgroup><option>' + PAGE + '</select>',
                 '<select><select>' + PAGE + '</select></select>',
                 '<select><select></select>' + PAGE + '</select>',
                 '<div><select></div>' + PAGE + '</select>',
                 '<select><option></option></optgroup>' + PAGE + '</select>',
                 '<select><input><textarea>unused</textarea>' + PAGE + '</select>',
                 '<select><table><tr><td>' + PAGE + '</td></tr></table></select>',
                 '<table><tr><td><select><option>' + PAGE + '</select></td></tr></table>',
                 '<select><form>' + PAGE + '</form></select>',
                 '<select><template></select>' + PAGE + '</template></select>',
                 '<select><script>"</select>"</script>' + PAGE + '</select>')
        for page in pages:
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, False)

    def test_native_fallback_and_button_contexts_cannot_supply_confirming_blocks(self):
        self.assert_fresh_page_contract(PAGE, True)
        for tag in ('option', 'optgroup', 'button', 'meter', 'progress', 'object', 'applet',
                    'audio', 'video', 'canvas', 'frameset'):
            for opening in ('>', '/>'):
                with self.subTest(tag=tag, opening=opening):
                    self.assert_fresh_page_contract('<' + tag + opening + PAGE + '</' + tag + '>', False)

    def test_ignored_nested_form_cannot_hide_a_visible_heading_qualifier(self):
        page = '<form>' + PAGE.replace('</h2>', '<form hidden> for a limited task</form></h2>') + '</form>'
        self.assert_fresh_page_contract(page, False)
        self.assert_fresh_page_contract('<form>' + PAGE + '</form>', True)
        self.assert_fresh_page_contract('<table><tr><td><form>' + PAGE + '</form></td></tr></table>', True)

    def test_foreign_content_and_integration_points_withhold_unproven_blocks(self):
        self.assert_fresh_page_contract(PAGE, True)
        pages = ('<svg>' + PAGE + '</svg>', '<math>' + PAGE + '</math>',
                 '<svg><foreignObject>' + PAGE + '</foreignObject></svg>',
                 '<svg><desc>' + PAGE + '</desc></svg>', '<svg><title>' + PAGE + '</title></svg>',
                 '<math><annotation-xml encoding="text/html">' + PAGE + '</annotation-xml></math>',
                 '<math><annotation-xml encoding="application/xhtml+xml">' + PAGE + '</annotation-xml></math>',
                 '<math><mi>' + PAGE + '</mi></math>', '<math><mtext>' + PAGE + '</mtext></math>',
                 '<svg><a href="/api/docs/models/fixture-code">' + PAGE + '</a></svg>',
                 '<svg><svg></svg>' + PAGE + '</svg>', '<svg><svg/>' + PAGE + '</svg>',
                 '<div><svg></div>' + PAGE + '</svg>', '<svg></math>' + PAGE + '</svg>',
                 '<math><svg/>' + PAGE + '</math>')
        for page in pages:
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, False)

    def test_content_scopes_preserve_visible_successors_and_hidden_inline_additions(self):
        for tag in ('select', 'option', 'optgroup', 'button', 'meter', 'progress', 'object', 'applet',
                    'audio', 'video', 'canvas', 'frameset', 'svg', 'math'):
            with self.subTest(tag=tag):
                self.assert_fresh_page_contract('<' + tag + '>unused</' + tag + '>' + PAGE, True)
                self.assert_fresh_page_contract('<div hidden><' + tag + '>unused</' + tag + '></div>' + PAGE, True)
        for prefix in ('<svg/>', '<math/>', '<svg><svg/></svg>', '<math><mtext/></math>',
                       '<select/><option/>unused</select>', '<template><select>' + PAGE + '</template>',
                       '<svg><foreignObject><select>unused</select></foreignObject></svg>'):
            with self.subTest(prefix=prefix):
                self.assert_fresh_page_contract(prefix + PAGE, True)
        self.assert_fresh_page_contract(PAGE.replace('</h2>', '<span hidden>unused</span></h2>')
                                       .replace('</p>', '<span hidden>unused</span></p>'), True)

    def test_content_scopes_cannot_supply_an_individual_heading_paragraph_or_link(self):
        heading, paragraph = '<h2>' + HEADING + '</h2>', '<p>' + LINKED + '</p>'
        link = '<a href="/api/docs/models/fixture-code">Fixture Code</a>'
        for tag in ('select', 'button', 'svg', 'math'):
            for original in (heading, paragraph, link):
                with self.subTest(tag=tag, original=original):
                    self.assert_fresh_page_contract(PAGE.replace(original, '<' + tag + '>' + original + '</' + tag + '>'), False)

    def test_ignored_document_and_table_tokens_cannot_hide_visible_qualifiers(self):
        for tag in ('html', 'head', 'body', 'caption', 'colgroup', 'tbody', 'thead', 'tfoot', 'tr', 'td', 'th'):
            page = PAGE.replace('</h2>', '<' + tag + ' hidden> for a limited task</' + tag + '></h2>')
            with self.subTest(tag=tag):
                self.assert_fresh_page_contract(page, False)
        self.assert_fresh_page_contract('<html><head><title>Models</title></head><body>' + PAGE + '</body></html>', True)

    def test_foreign_integration_controls_and_raw_bodies_cannot_fake_an_outer_close(self):
        pages = ('<svg><foreignObject><select></svg>' + PAGE + '</select></foreignObject></svg>',
                 '<math><mtext><select></math>' + PAGE + '</select></mtext></math>',
                 '<svg><foreignObject><template/></svg>' + PAGE + '</template></foreignObject></svg>',
                 '<svg><foreignObject><script/>"</svg>"' + PAGE + '</script></foreignObject></svg>',
                 '<svg><foreignObject><textarea/></svg>' + PAGE + '</textarea></foreignObject></svg>',
                 '<button><select></button>' + PAGE + '</select></button>')
        for page in pages:
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, False)
        for prefix in ('<svg><title/></svg>', '<svg><desc/></svg>',
                       '<select><xmp>unused</select>', '<select><plaintext>unused</select>',
                       '<svg><foreignObject><script/>unused</script></foreignObject></svg>'):
            with self.subTest(prefix=prefix):
                self.assert_fresh_page_contract(prefix + PAGE, True)

    def test_mixed_native_scopes_and_repeated_document_tokens_fail_closed(self):
        for page in ('<option><select></option>' + PAGE + '</select>',
                     '<optgroup><select></optgroup>' + PAGE + '</select>',
                     '<body>' + PAGE + '</body><body hidden>unused</body>',
                     '<html><body>' + PAGE + '</body></html><html hidden>unused</html>'):
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, False)
        self.assert_fresh_page_contract('<html><head><meta name="description"><body>' + PAGE + '</body></html>', True)
        self.assert_fresh_page_contract('<html><head hidden>' + PAGE + '</html>', True)

    def test_foreign_breakout_markup_does_not_turn_html_raw_or_template_flags_into_closes(self):
        for tag in ('svg', 'math'):
            for body in ('<div><script/>"</' + tag + '>"' + PAGE + '</script></div>',
                         '<p><textarea/></' + tag + '>' + PAGE + '</textarea></p>',
                         '<h2><template/></' + tag + '>' + PAGE + '</template></h2>'):
                with self.subTest(tag=tag, body=body):
                    self.assert_fresh_page_contract('<' + tag + '>' + body + '</' + tag + '>', False)
                    self.assert_fresh_page_contract('<' + tag + '>' + body + '</' + tag + '>' + PAGE, True)

    def test_content_scopes_exclude_pricing_without_erasing_visible_qualifiers(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(record['input'], record['output']) for record in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for tag in ('select', 'option', 'button', 'meter', 'progress', 'object', 'canvas', 'svg', 'math'):
            with self.subTest(tag=tag):
                self.assertEqual(rates('<' + tag + '>' + sample + '</' + tag + '>'), [])
                self.assertEqual(rates('<' + tag + '>unused</' + tag + '>' + sample), [(0.75, 4.5)])
                self.assertEqual(rates(sample.replace('Standard', 'Standard<' + tag + '>Batch</' + tag + '>')), [])
                self.assertEqual(rates(sample.replace('$0.75', '$<'+ tag + '>90</' + tag + '>0.75')), [])

    def test_foreign_raw_text_names_do_not_swallow_a_correctly_closed_visible_successor(self):
        for prefix in ('<svg><xmp>unused</svg>', '<svg><plaintext>unused</svg>',
                       '<math><textarea>unused</math>', '<math><noembed>unused</math>'):
            with self.subTest(prefix=prefix):
                self.assert_fresh_page_contract(prefix + PAGE, True)

    def test_raw_text_copies_cannot_confirm_or_authorize_fresh_acceptance(self):
        self.assert_fresh_page_contract(PAGE, True)
        for tag in ('script', 'style', 'xmp', 'iframe', 'noembed', 'noframes', 'noscript', 'textarea', 'title', 'plaintext'):
            for ending in ('>', '/>'):
                with self.subTest(tag=tag, ending=ending):
                    self.assert_fresh_page_contract('<' + tag + ending + PAGE + '</' + tag + '>', False)

    def test_hidden_ancestor_cannot_confirm_or_authorize_fresh_acceptance(self):
        self.assert_fresh_page_contract(PAGE, True)
        self.assert_fresh_page_contract('<div hidden>' + PAGE + '</div>', False)

    def test_hidden_block_start_cannot_join_fragments_across_a_paragraph_boundary(self):
        entry = {**ENTRY, 'paragraph': 'Use Fixture Code for complex reasoning and coding.'}
        positive = ('<h2>Choosing a model</h2><p>Use <a href="/api/docs/models/fixture-code">'
                    'Fixture Code</a> for complex reasoning and coding.</p>')
        # The div closes p even when hidden: the suffix is outside the leaf block.
        malformed = positive.replace(' for complex', '<div hidden>invisible boundary</div> for complex')
        with patch.dict(ENTRY, entry), patch(__name__ + '.PAGE', positive):
            self.assert_fresh_page_contract(positive, True)
            self.assert_fresh_page_contract(malformed, False)

    def test_implied_heading_list_and_cell_boundaries_precede_visibility(self):
        self.assert_fresh_page_contract(PAGE, True)
        heading = PAGE.replace(HEADING, 'Choosing<h3 hidden>unused</h3> a model')
        with self.subTest(context='heading'):
            self.assert_fresh_page_contract(heading, False)
        for tag, opening, closing in (('li', '<ul>', '</ul>'), ('dt', '<dl>', '</dl>'),
                                      ('dd', '<dl>', '</dl>'),
                                      ('td', '<table><tr>', '</tr></table>'),
                                      ('th', '<table><tr>', '</tr></table>')):
            for ending in ('>', '/>'):
                linked = LINKED.replace('our flagship', '<' + tag + ' hidden' + ending + 'unused</' + tag + '>our flagship')
                malformed = ('<h2>' + HEADING + '</h2>' + opening + '<' + tag + '>' + linked + '</' + tag + '>' + closing)
                with self.subTest(tag=tag, ending=ending):
                    self.assert_fresh_page_contract(malformed, False)

    def test_hidden_paragraph_implied_close_releases_valid_visible_successors(self):
        self.assert_fresh_page_contract(PAGE, True)
        for prefix in ('<p hidden>unused', '<p hidden/>unused', '<p><span hidden>unused'):
            with self.subTest(prefix=prefix):
                # Starting main closes the old p and ends its hidden inline scope.
                self.assert_fresh_page_contract(prefix + PAGE, True)

    def test_misnested_table_guidance_is_withdrawn_without_poisoning_a_valid_successor(self):
        self.assert_fresh_page_contract(PAGE, True)
        linked = LINKED.replace('our flagship', '<tr hidden><td>unused</td></tr>our flagship')
        malformed = '<table><h2>' + HEADING + '</h2><p>' + linked + '</p></table>'
        self.assert_fresh_page_contract(malformed, False)
        self.assert_fresh_page_contract(malformed + PAGE, True)
        self.assert_fresh_page_contract('<table><tbody><tr><td>' + PAGE + '</td></tr></tbody></table>', True)

    def test_paragraph_boundaries_cover_block_starts_and_preserve_hidden_inline_content(self):
        self.assertTrue(self.retrieve(PAGE)['guidance'])
        # Expected boundaries are fixture HTML, not derived from parser constants.
        tags = ('address', 'article', 'aside', 'blockquote', 'center', 'details', 'dialog', 'dir', 'div', 'dl', 'fieldset',
                'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header',
                'hgroup', 'hr', 'li', 'dd', 'dt', 'listing', 'main', 'menu', 'nav', 'ol', 'p', 'pre',
                'search', 'section', 'summary', 'table', 'ul', 'xmp')
        for tag in tags:
            for attribute in ('', ' hidden', ' HIDDEN="until-found"'):
                for ending in ('>', '/>'):
                    fragment = '<' + tag + attribute + ending + 'unused</' + tag + '>'
                    page = PAGE.replace('our flagship', fragment + 'our flagship')
                    with self.subTest(tag=tag, attribute=attribute, ending=ending):
                        self.assertEqual(self.retrieve(page)['guidance'], [])
                        self.assertTrue(self.retrieve(page + PAGE)['guidance'])
        for fragment in ('<span hidden>unused</span>', '<span hidden/>unused</span>',
                         '<span hidden><script/><div>literal boundary</div></script></span>',
                         '<template/><div hidden>inert boundary</div></template>'):
            with self.subTest(inline=fragment):
                self.assert_fresh_page_contract(PAGE.replace('our flagship', fragment + 'our flagship'), True)
        for fragment in ('<span hidden><div>boundary</div></span>', '<xmp hidden/><p>literal</p></xmp>',
                         '<div hidden><textarea/><p>literal</p></textarea></div>',
                         '<button hidden><div>scoped boundary</div></button>'):
            with self.subTest(block=fragment):
                page = PAGE.replace('our flagship', fragment + 'our flagship')
                self.assert_fresh_page_contract(page, False)
                self.assert_fresh_page_contract(page + PAGE, True)

    def test_valid_list_cell_and_omitted_paragraph_closes_remain_usable(self):
        for page in ('<ul><li>' + PAGE + '</li><li><ul><li>unused</li></ul></li></ul>',
                     '<dl><dt>Term</dt><dd>' + PAGE + '</dd></dl>',
                     '<table><tr><th>' + PAGE + '</th></tr></table>',
                     PAGE.replace('</p>', ''),
                     PAGE.replace('</p>', '').replace('<p>', '<p/>')):
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, True)

    def test_legacy_block_starts_also_end_a_paragraph_before_visibility_filtering(self):
        self.assert_fresh_page_contract(PAGE, True)
        for tag in ('center', 'dir'):
            with self.subTest(tag=tag):
                page = PAGE.replace('our flagship', '<' + tag + ' hidden/>unused</' + tag + '>our flagship')
                self.assert_fresh_page_contract(page, False)
                self.assert_fresh_page_contract(page + PAGE, True)

    def test_stray_paragraph_close_cannot_erase_an_empty_structural_boundary(self):
        self.assert_fresh_page_contract(PAGE, True)
        for fragment in ('</p>', '<div hidden>unused</div></p>',
                         '<p hidden/>unused<div hidden>boundary</div></p>'):
            with self.subTest(fragment=fragment):
                page = PAGE.replace('</h2>', '</h2>' + fragment)
                self.assert_fresh_page_contract(page, False)
                self.assert_fresh_page_contract(page + PAGE, True)
        self.assert_fresh_page_contract(PAGE.replace('</h2>', '</h2><span hidden></p></span>'), True)
        self.assert_fresh_page_contract(PAGE.replace('our flagship', '<button hidden></p></button>our flagship'), False)

    def test_block_interruption_withdraws_a_complete_but_malformed_reviewed_paragraph(self):
        self.assert_fresh_page_contract(PAGE, True)
        for fragment in ('<div>Only while access remains enabled.</div>',
                         '<span><div>Only while access remains enabled.</div></span>',
                         '<div hidden>unused</div>'):
            with self.subTest(fragment=fragment):
                page = PAGE.replace(LINKED, LINKED + fragment)
                self.assert_fresh_page_contract(page, False)
                self.assert_fresh_page_contract(page + PAGE, True)
        for tag in ('li', 'td', 'tr', 'tbody'):
            opening, closing = ('<ul><li>', '</li></ul>') if tag == 'li' else (
                '<table><tbody><tr><td>', '</td></tr></tbody></table>')
            with self.subTest(context=tag):
                page = opening + PAGE.replace(LINKED, LINKED + '<' + tag + ' hidden>unused</' + tag + '>') + closing
                self.assert_fresh_page_contract(page, False)
                self.assert_fresh_page_contract(page + PAGE, True)

    def test_hidden_attribute_presence_values_and_matched_blocks(self):
        self.assert_fresh_page_contract(PAGE, True)
        for attribute in ('hidden', 'HIDDEN', 'hidden=""', 'HiDdEn="hidden"', 'hidden="false"',
                          'hidden="until-found"', 'hidden="UNTIL-FOUND"', 'hidden="invalid"',
                          'hidden hidden="false"', 'class="old" class="new" hidden'):
            for opening in ('>', ' />'):
                for tag in ('div', 'h2', 'p'):
                    page = ('<div ' + attribute + opening + PAGE + '</div>' if tag == 'div' else
                            PAGE.replace('<' + tag + '>', '<' + tag + ' ' + attribute + opening))
                    with self.subTest(attribute=attribute, opening=opening, tag=tag):
                        self.assert_fresh_page_contract(page, False)

    def test_hidden_inline_text_and_required_links_use_only_visible_content(self):
        self.assert_fresh_page_contract(PAGE, True)
        link = '<a href="/api/docs/models/fixture-code">Fixture Code</a>'
        for opening in ('>', ' />'):
            hidden_span = '<span hidden' + opening
            pages = (PAGE.replace('Choosing a model', hidden_span + HEADING + '</span>'),
                     PAGE.replace('start, use ', 'start, ' + hidden_span + 'use </span>'),
                     PAGE.replace(link, link.replace('<a ', '<a hidden ').replace('">', '"' + opening)),
                     PAGE.replace(link, 'Fixture Code<a hidden href="/api/docs/models/fixture-code"' + opening + '</a>'))
            for page in pages:
                with self.subTest(opening=opening, page=page):
                    self.assert_fresh_page_contract(page, False)
            # Hidden additions are absent from rendered text, including hidden block order.
            for page in (PAGE.replace(HEADING, HEADING + hidden_span + 'old heading</span>'),
                         PAGE.replace('start, use ', 'start, ' + hidden_span + 'never </span>use '),
                         PAGE.replace('</h2>', '</h2><div hidden' + opening + '<p>Old copy</p></div>')):
                with self.subTest(opening=opening, visible=page):
                    self.assert_fresh_page_contract(page, True)

    def test_hidden_scopes_preserve_nesting_and_do_not_poison_visible_successors(self):
        self.assert_fresh_page_contract(PAGE, True)
        hidden = ('<div hidden><div>unused</div>' + PAGE + '</div>',
                  '<div hidden/><span>unused</span>' + PAGE + '</div>',
                  '<div hidden><div hidden>unused</div>' + PAGE + '</div>',
                  '<div hidden></div-other></span>' + PAGE,
                  '<div hidden><template/></template><script/>unused</script>' + PAGE + '</div>',
                  '<div hidden><span>' + PAGE + '</div>')
        for page in hidden:
            with self.subTest(page=page):
                self.assert_fresh_page_contract(page, False)
        for prefix in ('<div hidden><div>unused</div></div>',
                       '<div hidden/><span>unused</span></div>',
                       '<div hidden><span>unused</div>',
                       '<div hidden><template><p>unused</p></template><textarea/>unused</textarea></div>',
                       '<template/><div hidden>unused</div></template><script/>unused</script>'):
            with self.subTest(prefix=prefix):
                self.assert_fresh_page_contract(prefix + PAGE, True)
        self.assert_fresh_page_contract('<div hidden>' + PAGE + '</div>' + PAGE, True)
        self.assert_fresh_page_contract('<div hidden>' + PAGE + '</div>'
                                       + PAGE.replace('our flagship', 'our retired'), False)
        self.assert_fresh_page_contract(PAGE.replace('<h2>', '<h2 class="one" CLASS="two">'), False)
        self.assert_fresh_page_contract(PAGE.replace('href="/api/docs/models/fixture-code"',
                                                     'href="/api/docs/models/fixture-code" href="/other"'), False)
        self.assert_fresh_page_contract(PAGE.replace('<main>', '<main aria-hidden="true" data-hidden="true">'), True)

    def test_hidden_pricing_uses_only_visible_headings_tables_cells_and_text(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return [(record['input'], record['output']) for record in self.retrieve(page, url=SOURCES[2])['rates']]
        self.assertEqual(rates(sample), [(0.75, 4.5)])
        for opening in ('>', ' />'):
            for page in ('<div hidden' + opening + sample + '</div>',
                         sample.replace('<table>', '<table hidden' + opening),
                         sample.replace('<tr>', '<tr hidden' + opening),
                         sample.replace('<td>', '<td hidden' + opening)):
                with self.subTest(page=page):
                    self.assertEqual(rates(page), [])
            self.assertEqual(rates('<div hidden' + opening + sample + '</div>' + sample), [(0.75, 4.5)])
            self.assertEqual(rates(sample.replace('Standard', 'Standard<span hidden' + opening + ' Batch</span>')),
                             [(0.75, 4.5)])
            self.assertEqual(rates(sample.replace('$0.75', '<span hidden' + opening + '$0.75</span>')), [])
            self.assertEqual(rates(sample.replace('$0.75', '<span hidden' + opening + '$90</span>$0.75')), [(0.75, 4.5)])
            for tag in ('dialog', 'details'):
                self.assertEqual(rates('<' + tag + opening + sample + '</' + tag + '>'), [])
                self.assertEqual(rates('<' + tag + ' open' + opening + sample + '</' + tag + '>'), [(0.75, 4.5)])
                self.assertEqual(rates('<' + tag + opening + sample + '</' + tag + '>' + sample), [(0.75, 4.5)])
        self.assertEqual(rates('<details><summary>' + sample + '</summary></details>'), [(0.75, 4.5)])

    def test_closed_native_dialog_and_details_cannot_supply_confirmation(self):
        self.assert_fresh_page_contract(PAGE, True)
        for opening in ('>', ' />'):
            for tag in ('dialog', 'details'):
                prefix = '<' + tag + opening
                with self.subTest(tag=tag, opening=opening):
                    self.assert_fresh_page_contract(prefix + PAGE + '</' + tag + '>', False)
                    self.assert_fresh_page_contract('<' + tag + ' open' + opening + PAGE + '</' + tag + '>', True)
                    self.assert_fresh_page_contract(prefix + 'unused</' + tag + '>' + PAGE, True)
        self.assert_fresh_page_contract('<details><summary>Menu</summary>' + PAGE + '</details>', False)
        self.assert_fresh_page_contract('<details><summary>' + PAGE + '</summary></details>', True)
        self.assert_fresh_page_contract('<details><div><summary>' + PAGE + '</summary></div></details>', False)
        self.assert_fresh_page_contract('<details><summary>Menu</summary><summary>' + PAGE + '</summary></details>', False)
        self.assert_fresh_page_contract('<details hidden><summary>' + PAGE + '</summary></details>', False)
        self.assert_fresh_page_contract('<dialog open hidden>' + PAGE + '</dialog>', False)

    def test_nonrendered_metadata_and_hidden_inputs_do_not_break_visible_adjacency(self):
        self.assert_fresh_page_contract(PAGE, True)
        for element in ('<input type="hidden">', '<input TYPE="HiDdEn" />', '<meta name="description">',
                        '<link href="/unused">', '<base href="/unused">', '<param name="unused">',
                        '<source src="/unused">', '<track src="/unused">'):
            with self.subTest(element=element):
                self.assert_fresh_page_contract(PAGE.replace('</h2>', '</h2>' + element), True)
        # A duplicate type cannot hide a visible first type and erase its block.
        self.assert_fresh_page_contract(PAGE.replace('</h2>', '</h2><input type="text" type="hidden">'), False)

    def test_datalist_and_image_map_area_supply_no_rendered_blocks(self):
        self.assert_fresh_page_contract(PAGE, True)
        for opening in ('>', ' />'):
            with self.subTest(opening=opening):
                self.assert_fresh_page_contract('<datalist' + opening + PAGE + '</datalist>', False)
                self.assert_fresh_page_contract('<datalist' + opening + 'unused</datalist>' + PAGE, True)
                self.assert_fresh_page_contract(PAGE.replace('</h2>', '</h2><area href="/unused"' + opening), True)
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        self.assertEqual(self.retrieve('<datalist>' + sample + '</datalist>', url=SOURCES[2])['rates'], [])
        self.assertEqual([(record['input'], record['output']) for record in
                         self.retrieve('<datalist/>' + sample + '</datalist>' + sample, url=SOURCES[2])['rates']], [(0.75, 4.5)])

    def test_script_escaped_and_double_escaped_text_cannot_authorize_acceptance(self):
        self.assert_fresh_page_contract('<script>ordinary()</script>' + PAGE, True)
        for opening in ('<script>', '<script/>'):
            for escaped in ('<!--<script>', '<!--<ScRiPt >', '<!--<script/>', '<!--<script src="unused">'):
                with self.subTest(opening=opening, escaped=escaped):
                    self.assert_fresh_page_contract(opening + escaped + '</script>' + PAGE + '</script>', False)

    def test_script_transitions_keep_literal_closes_hidden_and_release_visible_guidance(self):
        hidden = ('<!--<script></script-other></scripture></script>',
                  '<!--<script>ignored<script></script>',
                  '<!--<script></script><script></script>',
                  '<!--<script></SCRIPT attr="unused">',
                  '<!--<script></script/>')
        for body in hidden:
            with self.subTest(body=body):
                self.assert_fresh_page_contract('<script/>' + body + PAGE + '</script>', False)
                self.assert_fresh_page_contract('<script/>' + body + '</script>' + PAGE, True)
        visible = ('ordinary()', '<!--ordinary()-->', '<!--<script>-->',
                   '<!--unused--><script>', '<!--><script>', '<!---><script>',
                   '<!--<scripture>', '<!--<script-other>', '<!--<script\v>', '<!--<script\u00a0>')
        for body in visible:
            with self.subTest(body=body):
                self.assert_fresh_page_contract('<script>' + body + '</script>' + PAGE, True)
        # </script in an ordinary script string really closes the HTML element.
        self.assert_fresh_page_contract('<script>"</script>' + PAGE, True)

    def test_script_states_apply_inside_templates_and_to_pricing(self):
        self.assert_fresh_page_contract('<template><script/><!--<script></script></template>' + PAGE
                                       + '</script></template>', False)
        self.assert_fresh_page_contract('<template><script/><!--<script></script></script></template>' + PAGE, True)
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        hidden = '<script/><!--<script></script>' + sample + '</script>'
        self.assertEqual(self.retrieve(hidden, url=SOURCES[2])['rates'], [])
        visible = '<script/><!--<script></script></script>' + sample
        self.assertEqual([(record['input'], record['output']) for record in self.retrieve(visible, url=SOURCES[2])['rates']],
                         [(0.75, 4.5)])

    def test_raw_text_cannot_supply_an_individual_heading_paragraph_or_link(self):
        paragraph = '<p>' + LINKED + '</p>'
        heading = '<h2>' + HEADING + '</h2>'
        link = '<a href="/api/docs/models/fixture-code">Fixture Code</a>'
        for tag in ('script', 'style', 'xmp', 'iframe', 'noembed', 'noframes', 'noscript', 'textarea', 'title'):
            for fragment in (heading, paragraph, link):
                with self.subTest(tag=tag, fragment=fragment):
                    replacement = ('Fixture Code' if fragment == link else '') + '<' + tag + '>' + fragment + '</' + tag + '>'
                    self.assert_page_contract(PAGE.replace(fragment, replacement), False)

    def test_raw_text_closes_only_at_its_own_end_and_plaintext_never_closes(self):
        for tag in ('script', 'style', 'xmp', 'iframe', 'noembed', 'noframes', 'noscript', 'textarea', 'title'):
            with self.subTest(tag=tag):
                self.assert_fresh_page_contract('<' + tag + '/><template></template><' + tag + '>'
                                               '</' + tag + '-other></main>' + PAGE, False)
                self.assert_fresh_page_contract('<template><' + tag + '/></template>' + PAGE
                                               + '</' + tag + '></template>', False)
                self.assert_fresh_page_contract('<' + tag + '/><template><' + tag + '>unused'
                                               + '</' + tag.upper() + ' >' + PAGE, True)
        self.assert_fresh_page_contract('<plaintext>' + PAGE + '</plaintext>' + PAGE, False)
        self.assert_fresh_page_contract('<plaintext/>' + PAGE + '</plaintext>' + PAGE, False)
        self.assert_fresh_page_contract('<template/><script/>unused</script></template>' + PAGE, True)

    def test_self_closing_flags_on_nonvoid_elements_preserve_their_html_scope(self):
        self.assert_page_contract(PAGE.replace('<h2>', '<h2/>').replace('<p>', '<p/>')
                                 .replace('<span>', '<span/>').replace('</h2>', '</h2><br/><img/>'), True)
        for tag in ('del', 's', 'strike', 'blockquote', 'q'):
            with self.subTest(tag=tag):
                self.assert_fresh_page_contract('<' + tag + '/>' + PAGE + '</' + tag + '>', False)
                self.assert_fresh_page_contract('<' + tag + '/>unused</' + tag + '>' + PAGE, True)

    def test_raw_text_pricing_copies_are_excluded_but_visible_tables_remain_usable(self):
        sample = fixtures.RecommendationTests.pricing_sample(self, '<h2>Standard</h2>')
        def rates(page):
            return self.retrieve(page, url=SOURCES[2])['rates']
        self.assertEqual([(record['input'], record['output']) for record in rates(sample)], [(0.75, 4.5)])
        for tag in ('script', 'style', 'xmp', 'iframe', 'noembed', 'noframes', 'noscript', 'textarea', 'title', 'plaintext'):
            for ending in ('>', '/>'):
                with self.subTest(tag=tag, ending=ending):
                    self.assertEqual(rates('<' + tag + ending + sample + '</' + tag + '>'), [])
                    visible = '<' + tag + ending + 'unused</' + tag + '>' + sample
                    self.assertEqual([(record['input'], record['output']) for record in rates(visible)],
                                     [] if tag == 'plaintext' else [(0.75, 4.5)])

    def test_inline_boundaries_preserve_rendered_heading_and_paragraph_spacing(self):
        for page in (PAGE.replace(HEADING, '<span>Choosing </span>a model'),
                     PAGE.replace('start, use ', 'start, <em>use </em>'),
                     PAGE.replace('complex reasoning and coding.', '<span>complex <b>reasoning </b>and </span>coding.')):
            with self.subTest(page=page):
                self.assert_page_contract(page, True)
        self.assert_page_contract(PAGE.replace('start, use ', 'start, <em>never use </em>'), False)

    def test_default_ignorable_characters_do_not_hide_real_word_changes(self):
        for invisible in ('\u034f', '\ufe0f', '\u115f', '\u2065', '\U000e0100'):
            with self.subTest(invisible=repr(invisible)):
                self.assert_page_contract(PAGE.replace('flagship', 'flag' + invisible + 'ship')
                                         .replace(HEADING, 'Choosing a mo' + invisible + 'del'), True)
        self.assert_page_contract(PAGE.replace('flagship', 'flag\u034fship unsuitable'), False)

    def test_boolean_and_noninteger_schema_versions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            listing, page = Path(temporary) / 'guidance.json', Path(temporary) / 'page.html'
            page.write_text(PAGE)
            for version in (True, False, 1.0, '1'):
                listing.write_text(json.dumps({'schema_version': version, 'entries': [ENTRY]}))
                with self.subTest(version=version, seam='loader'):
                    with self.assertRaises(ValueError):
                        load_reviewed_guidance(listing)
                with self.subTest(version=version, seam='OfficialSources'):
                    with patch('model_recommendations.load_reviewed_guidance', side_effect=lambda: load_reviewed_guidance(listing)):
                        evidence = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE).retrieve(urls=[SOURCES[0]])
                    self.assertEqual(evidence['guidance'], [])
                    self.assertIn('reviewed guidance list is invalid', evidence['sources'][0]['uncertainty'])
                with self.subTest(version=version, seam='check-model-guidance.py'):
                    result = subprocess.run([sys.executable, str(Path(__file__).with_name('check-model-guidance.py')),
                                             '--guidance', str(listing), '--page', SOURCES[0] + '=' + str(page)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn('invalid reviewed guidance list', result.stdout)

    def test_official_saved_cache_requires_every_current_reviewed_field(self):
        from model_evidence_cache import EvidenceCache
        discovery = {'revision': 'fixture', 'routes': deepcopy(self.routes)}
        changes = {'model_id': 'unlisted-code', 'provider': 'anthropic', 'label': 'Other label',
                   'tasks': ['analysis'], 'risks': ['ordinary'], 'source_url': SOURCES[3],
                   'text': 'Inferred coding fit', 'reviewed_at': '2026-10-04'}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cache.json'
            cache = EvidenceCache(lambda: fixtures.NOW, path, self.project)
            cache.retrieve(lambda: self.retrieve(PAGE), discovery)
            original = json.loads(path.read_text())
            for field, value in [*changes.items(), ('reviewed_at', None), ('removed_entry', None), ('changed_entry', None)]:
                with self.subTest(field=field):
                    saved = deepcopy(original)
                    claim = saved['entries'][SOURCES[0]]['guidance'][0]
                    reviewed = [ENTRY]
                    if field == 'removed_entry':
                        reviewed = []
                    elif field == 'changed_entry':
                        reviewed = [{**ENTRY, 'paragraph': PARAGRAPH + ' Only for a preview.'}]
                    elif value is None:
                        claim.pop(field)
                    else:
                        claim[field] = value
                    path.write_text(json.dumps(saved))
                    fetched = []
                    def offline(url):
                        fetched.append(url)
                        raise OSError('Controlled source unavailable')
                    official = OfficialSources(lambda: fixtures.NOW, fetch=offline, reviewed=reviewed)
                    result = cache.retrieve(official.retrieve, discovery)
                    self.assertIn(SOURCES[0], fetched, 'Nonmatching guidance must make its source due')
                    self.assertEqual(result['guidance'], [])
                    self.assertEqual(json.loads(path.read_text())['entries'][SOURCES[0]]['guidance'], [])

    def test_official_matching_cache_keeps_inclusive_24_hour_confirmation(self):
        from model_evidence_cache import EvidenceCache
        now = [fixtures.NOW]
        fetched = []
        def fetch(url):
            fetched.append(url)
            return PAGE if url == SOURCES[0] else '<p>Unknown</p>'
        official = OfficialSources(lambda: now[0], fetch=fetch, reviewed=[ENTRY])
        discovery = {'revision': 'fixture', 'routes': deepcopy(self.routes)}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cache.json'
            EvidenceCache(lambda: now[0], path, self.project).retrieve(official.retrieve, discovery)
            for age in (86399, 86400, 86401):
                with self.subTest(age=age):
                    now[0] = (datetime.fromisoformat(fixtures.NOW.replace('Z', '+00:00')) + timedelta(seconds=age)).isoformat()
                    fetched.clear()
                    result = EvidenceCache(lambda: now[0], path, self.project).retrieve(official.retrieve, discovery)
                    self.assertEqual(SOURCES[0] in fetched, age > 86400)
                    self.assertEqual(len(result['guidance']), 1)
                    self.assertEqual(result['guidance'][0]['checked_at'], now[0] if age > 86400 else fixtures.NOW)

    def test_official_configuration_rejects_legacy_cache_and_retained_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            controlled = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                       recommendation_sources=lambda: deepcopy(self.evidence), evidence_dir=Path(temporary))
            legacy = controlled.read()
            self.assertIn('Accept replacement', legacy['choices'])
            fetched = []
            def offline(url):
                fetched.append(url)
                raise OSError('Controlled source unavailable')
            official = OfficialSources(lambda: fixtures.NOW, fetch=offline, reviewed=[ENTRY])
            service = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                    recommendation_sources=official.retrieve, evidence_dir=Path(temporary))
            with self.subTest(seam='read'):
                draft = service.read()
                self.assertIn(SOURCES[0], fetched)
                self.assertNotIn('Accept replacement', draft['choices'])
                self.assertEqual(draft['recommendation_evidence']['guidance'], [])
                self.assertIn('No reviewed guidance yet for fixture-analysis.', draft['recommendations']['implementation']['rationale'])
                self.assertIn('Reviewed guidance withdrawn for fixture-code: ' + WITHDRAWN, draft['recommendations']['implementation']['rationale'])
            fetched.clear()
            with self.subTest(seam='retained Accept'):
                accepted = service.reply(legacy, 'Accept replacement')
                self.assertEqual(accepted['after'], legacy['after'])
                self.assertNotIn('Accept replacement', accepted['choices'])
                self.assertIsNone(accepted['recommendations']['implementation']['choice'])
            self.assertEqual(fetched, [])
            self.assertEqual(self.state.read_bytes(), self.original)
            self.assertFalse((self.project / '.playbook-config.json').exists())

    def test_retained_official_advice_is_withheld_after_reviewed_list_changes(self):
        for changed in ([], [{**ENTRY, 'reviewed_at': '2026-10-06'}], [{**ENTRY, 'paragraph': PARAGRAPH + ' Only in preview.'}]):
            with self.subTest(reviewed=changed):
                fetched = []
                def fetch(url):
                    fetched.append(url)
                    return PAGE if url == SOURCES[0] else '<p>Unknown</p>'
                with patch('model_recommendations.load_reviewed_guidance', return_value=[ENTRY]):
                    official = OfficialSources(lambda: fixtures.NOW, fetch=fetch)
                    service = self.service(sources=official.retrieve)
                    draft = service.read()
                self.assertIn('Accept replacement', draft['choices'])
                fetched.clear()
                with patch('model_recommendations.load_reviewed_guidance', return_value=changed):
                    for reply in ('Accept replacement', 'Explain Build'):
                        with self.subTest(reply=reply):
                            result = service.reply(draft, reply)
                            self.assertEqual(result['after'], draft['after'])
                            self.assertIsNone(result['recommendations']['implementation']['choice'])
                            self.assertNotIn('Accept replacement', result['choices'])
                self.assertEqual(fetched, [SOURCES[0]], 'Accept rechecks; Explain only projects cached advice')
                self.assertEqual(self.state.read_bytes(), self.original)

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

    def test_official_cli_pins_configuration_and_source_clocks(self):
        with tempfile.TemporaryDirectory() as temporary:
            draft = self.official_cli('read', {'context': self.context}, Path(temporary),
                                      pages={SOURCES[0]: PAGE}, reviewed=[ENTRY])
            self.assertIn('Accept replacement', draft['choices'])
            self.assertEqual(draft['recommendation_evidence']['guidance'][0]['checked_at'], fixtures.NOW.replace('Z', '+00:00'))
            self.assertNotIn('status', draft['recommendations']['implementation']['guidance'])

    def test_accept_fetches_only_original_source_and_refuses_unavailable_or_withdrawn(self):
        for outcome in ('confirmed', 'unavailable', 'withdrawn', 'changed_entry', 'route_changed', 'permission'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as temporary:
                pages, entries, fetched = {SOURCES[0]: PAGE}, [deepcopy(ENTRY)], []
                def fetch(url):
                    fetched.append(url)
                    if not pages:
                        raise OSError('Controlled source unavailable')
                    return pages.get(url, '<p>Unknown</p>')
                official = OfficialSources(lambda: fixtures.NOW, fetch=fetch, reviewed=entries)
                service = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                        recommendation_sources=official.retrieve, evidence_dir=Path(temporary))
                original = service.read()
                (self.project / '.playbook-config.json').write_text(json.dumps(
                    {'schema_version': 1, 'adopted': True, 'models': original['before']}))
                original = service.read()
                self.assertIn('Accept replacement', original['choices'])
                # Advisory reads retain the ordinary fresh confirmation cache.
                fetched.clear()
                self.assertIn('Accept replacement', service.read()['choices'])
                self.assertNotIn(SOURCES[0], fetched)
                if outcome == 'unavailable':
                    pages.clear()
                elif outcome == 'withdrawn':
                    pages[SOURCES[0]] = PAGE.replace('our flagship', 'our retired')
                elif outcome == 'changed_entry':
                    entries[0]['heading'] = 'Changed heading'
                    pages[SOURCES[0]] = PAGE.replace(HEADING, 'Changed heading')
                elif outcome == 'route_changed':
                    self.routes.append({**self.routes[0], 'model_id': 'unlisted-new'})
                elif outcome == 'permission':
                    original['context']['constraints'] = {original['replacement']['role']: {'permission': False}}
                    original['proposal_revision'] = Configuration._revision(original)
                (self.project / 'approved.json').write_bytes(b'{"approved": "keep"}\n')
                project_before = {path.name: path.read_bytes() for path in self.project.iterdir()}
                original_before = deepcopy(original)
                fetched.clear()
                result = service.reply(original, 'Accept replacement')
                self.assertEqual(fetched, [SOURCES[0]], 'Each acceptance checks only the original official source once')
                self.assertEqual(original, original_before)
                self.assertEqual({path.name: path.read_bytes() for path in self.project.iterdir()}, project_before)
                if outcome == 'confirmed':
                    self.assertEqual(result['step'], 'preview')
                    self.assertEqual(result['after'][original['replacement']['role']]['model_id'], 'fixture-code')
                else:
                    self.assertEqual(result['after'], original['after'])
                    self.assertNotIn('Accept replacement', result['choices'])
                    self.assertIn('Draft retained', result['message'])
                    if outcome == 'withdrawn':
                        self.assertIn(WITHDRAWN, result['message'])
                    if outcome == 'unavailable':
                        self.assertIn('unavailable', result['message'])
                if outcome == 'route_changed':
                    self.routes.pop()

    def test_accept_fresh_confirmation_is_independent_of_cache_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            pages, fetched = {SOURCES[0]: PAGE}, []
            def fetch(url):
                fetched.append(url)
                return pages.get(url, '<p>Unknown</p>')
            official = OfficialSources(lambda: fixtures.NOW, fetch=fetch, reviewed=[ENTRY])
            service = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                    recommendation_sources=official.retrieve, evidence_dir=Path(temporary))
            original = service.read()
            self.assertIn('Accept replacement', original['choices'])
            pages[SOURCES[0]] = PAGE.replace('our flagship', 'our retired')
            withdrawn = service.reply(original, 'Refresh')
            self.assertNotIn('Accept replacement', withdrawn['choices'])
            disk_before = service.evidence_cache.path.read_bytes()
            pages[SOURCES[0]] = PAGE
            fetched.clear()
            with patch('model_evidence_cache.os.replace', side_effect=OSError('Controlled persistence failure')):
                result = service.reply(original, 'Accept replacement')
            self.assertEqual(fetched, [SOURCES[0]])
            self.assertEqual(result['step'], 'preview')
            self.assertEqual(result['after'][original['replacement']['role']]['model_id'], 'fixture-code')
            self.assertEqual(service.evidence_cache.path.read_bytes(), disk_before)
            self.assertEqual(self.state.read_bytes(), self.original)

    def test_cli_accept_rechecks_after_unpublished_withdrawal_across_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache, log = Path(temporary) / 'cache', Path(temporary) / 'fetches'
            pages = {SOURCES[0]: PAGE}
            original = self.official_cli('read', {'context': self.context}, cache, pages=pages, reviewed=[ENTRY])
            (self.project / '.playbook-config.json').write_text(json.dumps(
                {'schema_version': 1, 'adopted': True, 'models': original['before']}))
            (self.project / 'approved.json').write_bytes(b'{"approved": "keep"}\n')
            original = self.official_cli('read', {'context': self.context}, cache, pages=pages, reviewed=[ENTRY])
            self.assertIn('Accept replacement', original['choices'])
            self.assertIsNotNone(original['recommendations'][original['replacement']['role']]['choice'])
            # A retained recovery proposal also starts with usable advice.
            recovery = self.official_cli('reply', {'proposal': original}, cache, expected_code=2,
                                         pages=pages, reviewed=[ENTRY])
            self.assertIn('Accept replacement', recovery['retained_proposal']['choices'])
            disk_before = {path.name: path.read_bytes() for path in cache.iterdir()}
            project_before = {path.name: path.read_bytes() for path in self.project.iterdir()}
            pages[SOURCES[0]] = PAGE.replace('our flagship', 'our retired')
            withdrawn = self.official_cli('reply', {'proposal': original, 'reply': 'Refresh'}, cache,
                                          pages=pages, reviewed=[ENTRY], now='2026-10-01T12:01:00Z', fail_cache_write=True)
            self.assertNotIn('Accept replacement', withdrawn['choices'])
            self.assertTrue(withdrawn['recommendation_evidence']['changes'])
            self.assertFalse(withdrawn['recommendation_evidence']['cache_persisted'])
            self.assertEqual({path.name: path.read_bytes() for path in cache.iterdir()}, disk_before)
            restored = self.official_cli('reply', {'proposal': recovery, 'reply': 'Back'}, cache,
                                         pages=pages, reviewed=[ENTRY], now='2026-10-01T12:02:00Z')
            self.assertIn('Accept replacement', restored['choices'], 'Cached advisory display still uses its freshness rules')
            for retained in (original, recovery['retained_proposal'], restored):
                for page in (None, pages, {SOURCES[0]: '<div hidden>' + PAGE + '</div>'}, {SOURCES[0]: PAGE}):
                    log.write_text('')
                    result = self.official_cli('reply', {'proposal': retained, 'reply': 'Accept replacement'}, cache,
                                               pages=page, reviewed=[ENTRY], now='2026-10-01T12:02:00Z',
                                               fail_cache_write=True, fetch_log=log)
                    self.assertEqual(log.read_text().splitlines(), [SOURCES[0]])
                    self.assertEqual({path.name: path.read_bytes() for path in self.project.iterdir()}, project_before)
                    self.assertEqual({path.name: path.read_bytes() for path in cache.iterdir()}, disk_before)
                    if page is not None and page[SOURCES[0]] == PAGE:
                        self.assertEqual(result['step'], 'preview')
                        self.assertEqual(result['after'][original['replacement']['role']]['model_id'], 'fixture-code')
                    else:
                        self.assertEqual(result['after'], original['after'])
                        self.assertNotIn('Accept replacement', result['choices'])
                        self.assertIn('unavailable' if page is None else WITHDRAWN, result['message'])

    def test_cli_accept_rechecks_a_fresh_cache_and_binds_current_reviewed_entry(self):
        for changed in ('confirmed', 'unavailable', 'withdrawn', 'changed_entry'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                cache, log = Path(temporary) / 'cache', Path(temporary) / 'fetches'
                original = self.official_cli('read', {'context': self.context}, cache,
                                              pages={SOURCES[0]: PAGE}, reviewed=[ENTRY])
                (self.project / '.playbook-config.json').write_text(json.dumps(
                    {'schema_version': 1, 'adopted': True, 'models': original['before']}))
                original = self.official_cli('read', {'context': self.context}, cache,
                                              pages={SOURCES[0]: PAGE}, reviewed=[ENTRY])
                self.assertIn('Accept replacement', original['choices'])
                entries = [{**ENTRY, 'heading': 'Changed heading'}] if changed == 'changed_entry' else [ENTRY]
                pages = None if changed == 'unavailable' else {SOURCES[0]:
                         PAGE.replace('our flagship', 'our retired') if changed == 'withdrawn' else
                         PAGE.replace(HEADING, 'Changed heading') if changed == 'changed_entry' else PAGE}
                (self.project / 'approved.json').write_bytes(b'{"approved": "keep"}\n')
                project_before = {path.name: path.read_bytes() for path in self.project.iterdir()}
                result = self.official_cli('reply', {'proposal': original, 'reply': 'Accept replacement'}, cache,
                                           pages=pages, reviewed=entries, fetch_log=log)
                self.assertEqual(log.read_text().splitlines(), [SOURCES[0]])
                self.assertEqual({path.name: path.read_bytes() for path in self.project.iterdir()}, project_before)
                if changed == 'confirmed':
                    self.assertEqual(result['step'], 'preview')
                else:
                    self.assertEqual(result['after'], original['after'])
                    self.assertNotIn('Accept replacement', result['choices'])

    def test_accept_withdrawal_never_reranks_to_another_confirmed_entry(self):
        alternative = {**ENTRY, 'model_id': 'fixture-analysis', 'label': 'Fixture Analysis',
                       'heading': 'Another reviewed model', 'paragraph': 'Use Fixture Analysis for coding.',
                       'link': '/api/docs/models/fixture-analysis'}
        other_page = ('<h2>Another reviewed model</h2><p>Use <a href="/api/docs/models/fixture-analysis">'
                      'Fixture Analysis</a> for coding.</p>')
        with tempfile.TemporaryDirectory() as temporary:
            pages, fetched = {SOURCES[0]: PAGE + other_page}, []
            def fetch(url):
                fetched.append(url)
                return pages.get(url, '<p>Unknown</p>')
            official = OfficialSources(lambda: fixtures.NOW, fetch=fetch, reviewed=[ENTRY, alternative])
            cache = Path(temporary) / 'cache'
            service = Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                    recommendation_sources=official.retrieve, evidence_dir=cache)
            original = service.read()
            self.assertIn('Accept replacement', original['choices'])
            self.assertEqual(original['replacement']['advice']['choice']['model_id'], 'fixture-code')
            cli_original = self.official_cli('read', {'context': self.context}, cache,
                                              pages=pages, reviewed=[ENTRY, alternative])
            self.assertIn('Accept replacement', cli_original['choices'])
            pages[SOURCES[0]] = PAGE.replace('our flagship', 'our retired') + other_page
            fetched.clear()
            refused = service.reply(original, 'Accept replacement')
            self.assertEqual(fetched, [SOURCES[0]])
            self.assertEqual(refused['after'], original['after'])
            self.assertIsNone(refused['replacement']['advice']['choice'])
            self.assertEqual([record['model_id'] for record in service.evidence_cache.saved['entries'][SOURCES[0]]['guidance']],
                             ['fixture-analysis'], 'Another confirmed entry exists, but cannot replace the original proposal')
            log = Path(temporary) / 'fetches'
            refused = self.official_cli('reply', {'proposal': cli_original, 'reply': 'Accept replacement'}, cache,
                                        pages=pages, reviewed=[ENTRY, alternative], fetch_log=log)
            self.assertEqual(log.read_text().splitlines(), [SOURCES[0]])
            self.assertEqual(refused['after'], original['after'])
            self.assertIsNone(refused['replacement']['advice']['choice'])
            self.assertEqual(self.state.read_bytes(), self.original)

    def test_accept_source_check_does_not_consume_normal_discovery_refresh(self):
        fetched = []
        def fetch(url):
            fetched.append(url)
            return PAGE if url == SOURCES[0] else '<p>Unknown</p>'
        official = OfficialSources(lambda: fixtures.NOW, fetch=fetch, reviewed=[ENTRY])
        service = self.service(sources=official.retrieve)
        original = service.read()
        self.assertIn('Accept replacement', original['choices'])
        self.routes.append({**self.routes[0], 'model_id': 'unlisted-new'})
        fetched.clear()
        refused = service.reply(original, 'Accept replacement')
        self.assertEqual(refused['after'], original['after'])
        self.assertEqual(fetched, [SOURCES[0]])
        fetched.clear()
        service.read()
        self.assertIn(SOURCES[1], fetched, 'The ordinary new-model discovery pass must still recheck its other sources')

    def test_complete_entry_binding_and_semantic_change_notice(self):
        from model_evidence_cache import EvidenceCache
        from model_recommendations import matches_reviewed_guidance
        discovery = {'revision': 'fixture', 'routes': deepcopy(self.routes)}
        for changed, expected_changes in (({**ENTRY, 'heading': 'Changed heading'}, 1),
                                          ({**ENTRY, 'paragraph': PARAGRAPH + ' '}, 0),
                                          ({**ENTRY, 'tasks': ['coding', 'analysis']}, 1),
                                          ({**ENTRY, 'reviewed_at': '2026-10-06'}, 0)):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                cache = EvidenceCache(lambda: fixtures.NOW, Path(temporary) / 'cache.json', self.project)
                original = cache.retrieve(OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE, reviewed=[ENTRY]).retrieve, discovery)
                record = original['guidance'][0]
                self.assertFalse(matches_reviewed_guidance(record, [changed]))
                legacy = deepcopy(record)
                legacy.pop('entry_fingerprint', None)
                self.assertFalse(matches_reviewed_guidance(legacy, [ENTRY]))
                changed_source = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE, reviewed=[changed])
                updated = cache.retrieve(changed_source.retrieve, discovery, force=True)
                self.assertEqual(len(updated['changes']), expected_changes)
                if expected_changes:
                    self.assertEqual(updated['changes'][0]['before']['guidance'],
                                     [{'model_id': 'fixture-code', 'label': 'Fixture Code', 'provider': 'openai',
                                       'tasks': ['coding'], 'risks': ['ordinary', 'high'], 'text': PARAGRAPH, 'source_url': SOURCES[0]}])
                equal = cache.retrieve(changed_source.retrieve, discovery, force=True)
                self.assertEqual(equal['changes'], [])

    def test_list_removal_reports_change_even_when_refresh_is_incomplete(self):
        from model_evidence_cache import EvidenceCache
        cache = EvidenceCache(lambda: fixtures.NOW)
        discovery = {'revision': 'fixture', 'routes': deepcopy(self.routes)}
        original = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE, reviewed=[ENTRY])
        cache.retrieve(original.retrieve, discovery)
        removed = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE, reviewed=[])
        result = cache.retrieve(removed.retrieve, discovery, force=True)
        self.assertEqual(result['guidance'], [])
        self.assertEqual([change['source_url'] for change in result['changes']], [SOURCES[0]])
        self.assertEqual(cache.retrieve(removed.retrieve, discovery, force=True)['changes'], [])

    def test_cache_drops_malformed_records_without_breaking_change_comparison(self):
        from model_evidence_cache import EvidenceCache
        discovery = {'revision': 'fixture', 'routes': deepcopy(self.routes)}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cache.json'
            cache = EvidenceCache(lambda: fixtures.NOW, path, self.project)
            cache.retrieve(lambda: self.retrieve(PAGE), discovery)
            saved = json.loads(path.read_text())
            for malformed in (None, 1, [], 'legacy claim'):
                with self.subTest(record=malformed):
                    saved['entries'][SOURCES[0]]['guidance'] = [malformed]
                    path.write_text(json.dumps(saved))
                    official = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE, reviewed=[ENTRY])
                    result = cache.retrieve(official.retrieve, discovery)
                    self.assertEqual([record['model_id'] for record in result['guidance']], ['fixture-code'])

    def test_retained_claim_checks_latest_successful_withdrawal_and_full_entry(self):
        for changed_list in (False, True):
            with self.subTest(changed_list=changed_list), tempfile.TemporaryDirectory() as temporary:
                cache = Path(temporary)
                pages, entries, now = {SOURCES[0]: PAGE}, [deepcopy(ENTRY)], [fixtures.NOW]
                official = OfficialSources(lambda: now[0], fetch=lambda url: pages.get(url, '<p>Unknown</p>'), reviewed=entries)
                service = Configuration(self.project, self.discover, lambda: now[0], context=self.context,
                                        recommendation_sources=official.retrieve, evidence_dir=cache)
                original = service.read()
                self.assertIn('Accept replacement', original['choices'])
                cli_original = self.official_cli('read', {'context': self.context}, cache, pages=pages, reviewed=entries)
                self.assertIn('Accept replacement', cli_original['choices'])
                self.assertEqual(cli_original['recommendation_evidence']['guidance'][0]['checked_at'], fixtures.NOW)
                if changed_list:
                    entries[0]['heading'] = 'Changed heading'
                    for seam in ('Configuration', 'CLI'):
                        with self.subTest(seam=seam, before_refresh=True):
                            result = (service.reply(original, 'Accept replacement') if seam == 'Configuration' else
                                      self.official_cli('reply', {'proposal': cli_original, 'reply': 'Accept replacement'}, cache,
                                                        pages=pages, reviewed=entries))
                            self.assertEqual(result['after'], original['after'])
                            self.assertNotIn('Accept replacement', result['choices'])
                else:
                    pages[SOURCES[0]] = PAGE.replace('our flagship', 'our retired')
                now[0] = '2026-10-01T12:01:00Z'
                withdrawn = service.reply(original, 'Refresh')
                self.assertNotIn('Accept replacement', withdrawn['choices'])
                self.assertEqual(len(withdrawn['recommendation_evidence']['changes']), 0 if changed_list else 1,
                                 'A prior Accept source check already recorded a changed-list withdrawal')
                for reply in ('Accept replacement', 'Explain Build'):
                    result = service.reply(original, reply)
                    self.assertEqual(result['after'], original['after'])
                    self.assertNotIn('Accept replacement', result['choices'])
                    self.assertIsNone(result['recommendations']['implementation']['choice'])
                accepted = self.official_cli('reply', {'proposal': cli_original, 'reply': 'Accept replacement'}, cache,
                                            pages=pages, reviewed=entries, now=now[0])
                self.assertEqual(accepted['after'], cli_original['after'])
                self.assertNotIn('Accept replacement', accepted['choices'])
                recovery = self.official_cli('reply', {'proposal': cli_original}, cache, expected_code=2,
                                            pages=pages, reviewed=entries, now=now[0])
                self.assertNotIn('Accept replacement', recovery['retained_proposal']['choices'])
                self.assertEqual(self.state.read_bytes(), self.original)

    def test_duplicate_confirming_attributes_withdraw_at_all_seams(self):
        for replacement in ('href="/api/docs/models/fixture-other" href="/api/docs/models/fixture-code"',
                            'href="/api/docs/models/fixture-code" HREF="/api/docs/models/fixture-other"',
                            'href="/api/docs/models/fixture-code" title="a" title="b"'):
            with self.subTest(replacement=replacement):
                self.assert_page_contract(PAGE.replace('href="/api/docs/models/fixture-code"', replacement), False)
        self.assert_page_contract(PAGE.replace('<h2>', '<h2 id="a" id="b">'), False)

    def test_duplicate_json_keys_and_provider_labels_reject_whole_list(self):
        claude = {**ENTRY, 'provider': 'anthropic', 'model_id': 'claude-fixture', 'source_url': SOURCES[3],
                  'link': '/docs/en/about-claude/models/claude-fixture'}
        for listing in (json.dumps({'schema_version': 1, 'entries': [ENTRY]}).replace('"heading":', '"heading": "Unreviewed", "heading":'),
                        json.dumps({'schema_version': 1, 'entries': [ENTRY]}).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
                        json.dumps({'schema_version': 1, 'entries': [ENTRY, {**ENTRY, 'model_id': 'fixture-other', 'link': '/api/docs/models/fixture-other'}]}),
                        json.dumps({'schema_version': 1, 'entries': [ENTRY, claude, {**claude, 'model_id': 'claude-other', 'link': '/docs/models/claude-other'}]})):
            with self.subTest(listing=listing), tempfile.TemporaryDirectory() as temporary:
                path, page = Path(temporary) / 'guidance.json', Path(temporary) / 'page.html'
                path.write_text(listing)
                page.write_text(PAGE)
                with self.subTest(seam='loader'), self.assertRaises(ValueError):
                    load_reviewed_guidance(path)
                with patch('model_recommendations.load_reviewed_guidance', side_effect=lambda: load_reviewed_guidance(path)):
                    evidence = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE).retrieve()
                    with self.subTest(seam='OfficialSources'):
                        self.assertEqual(evidence['guidance'], [])
                    with self.subTest(seam='Configuration'):
                        self.assertNotIn('Accept replacement', self.service(sources=lambda: evidence).read()['choices'])
                checked = subprocess.run([sys.executable, str(Path(__file__).with_name('check-model-guidance.py')),
                                          '--guidance', str(path), '--page', SOURCES[0] + '=' + str(page)], capture_output=True, text=True)
                with self.subTest(seam='release check'):
                    self.assertEqual(checked.returncode, 2, checked.stdout + checked.stderr)
                with self.subTest(seam='public CLI'):
                    result = self.official_cli('read', {'context': self.context}, Path(temporary) / 'cache', listing=path,
                                               pages={SOURCES[0]: PAGE})
                    self.assertEqual(result['recommendation_evidence']['guidance'], [])
                    self.assertNotIn('Accept replacement', result['choices'])

    def test_known_withdrawal_survives_failed_cache_write_and_constructor_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / 'cache'
            pages = {SOURCES[0]: PAGE}
            now = [fixtures.NOW]
            official = OfficialSources(lambda: now[0], fetch=lambda url: pages.get(url, '<p>Unknown</p>'), reviewed=[ENTRY])
            service = Configuration(self.project, self.discover, lambda: now[0], context=self.context,
                                    recommendation_sources=official.retrieve, evidence_dir=cache)
            original = service.read()
            self.assertIn('Accept replacement', original['choices'])
            cli_original = self.official_cli('read', {'context': self.context}, cache, pages=pages, reviewed=[ENTRY])
            self.assertIn('Accept replacement', cli_original['choices'])
            pages[SOURCES[0]] = PAGE.replace('our flagship', 'our retired')
            now[0] = '2026-10-01T12:01:00Z'
            with patch('model_evidence_cache.os.replace', side_effect=OSError('Controlled persistence failure')):
                service.reply(original, 'Refresh')
            with self.subTest(seam='cache write failure'):
                result = service.reply(original, 'Accept replacement')
                self.assertEqual(result['after'], original['after'])
                self.assertNotIn('Accept replacement', result['choices'])
            service.reply(original, 'Refresh')
            for unavailable in (False, True):
                with self.subTest(seam='CLI constructor recovery', unavailable=unavailable):
                    # A project-local evidence destination rejects construction before a service exists.
                    error = self.official_cli('reply', {'proposal': original}, self.project / 'invalid-cache' if unavailable else cache,
                                              expected_code=2, pages=pages, reviewed=[ENTRY], now=now[0])
                    self.assertNotIn('Accept replacement', error['retained_proposal']['choices'])

    def test_shared_cache_withdrawal_wins_over_unpersisted_confirmation_at_equal_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            pages = {SOURCES[0]: PAGE}
            official = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: pages.get(url, '<p>Unknown</p>'), reviewed=[ENTRY])
            def service():
                return Configuration(self.project, self.discover, lambda: fixtures.NOW, context=self.context,
                                     recommendation_sources=official.retrieve, evidence_dir=Path(temporary))
            first = service()
            original = first.read()
            with patch('model_evidence_cache.os.replace', side_effect=OSError('Controlled persistence failure')):
                first.reply(original, 'Refresh')
            pages[SOURCES[0]] = PAGE.replace('our flagship', 'our retired')
            service().reply(original, 'Refresh')
            result = first.reply(original, 'Accept replacement')
            self.assertEqual(result['after'], original['after'])
            self.assertNotIn('Accept replacement', result['choices'])

    def test_successful_withdrawal_drops_retained_price_label_in_same_check(self):
        entry, page = fixtures.REVIEWED_CLAUDE, fixtures.REVIEWED_CLAUDE_PAGE
        pricing = ('<p>All prices are in USD.</p><h2>Model pricing</h2><table><tr><th>Name</th><th>Input</th><th>Output</th>'
                   '<th>5m writes</th><th>1h writes</th><th>Hits and refreshes</th></tr><tr><td>Claude Fixture 1.0</td>'
                   '<td>$3 / MTok</td><td>$8 / MTok</td><td>-</td><td>-</td><td>-</td></tr></table>')
        original = self.retrieve(page, entries=[entry], url=SOURCES[3])['guidance']
        pages = {SOURCES[3]: page.replace('complex coding', 'not coding'), SOURCES[4]: pricing}
        official = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: pages[url], reviewed=[entry])
        result = official.retrieve(urls=[SOURCES[3], SOURCES[4]], retained_guidance=original)
        self.assertEqual(result['guidance'], [])
        self.assertEqual(result['rates'], [])
        replayed = official.retrieve(urls=[SOURCES[4]], retained_guidance=original)
        self.assertEqual(replayed['rates'], [])

    def test_withdrawn_and_unlisted_notices_are_distinct(self):
        official = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE.replace('our flagship', 'our retired'), reviewed=[ENTRY])
        advice = self.service(sources=official.retrieve).read()['recommendations']['implementation']
        for field in ('rationale', 'limitations'):
            self.assertIn('No reviewed guidance yet for fixture-analysis', advice[field])
            self.assertIn('Reviewed guidance withdrawn for fixture-code: ' + WITHDRAWN, advice[field])
            self.assertNotIn('No reviewed guidance yet for fixture-analysis, fixture-code', advice[field])

    def test_public_cli_imports_from_external_cwd_with_only_offline_hooks(self):
        scripts = str(Path(__file__).resolve().parent)
        bootstrap = 'import sys; sys.path.insert(0, ' + repr(scripts) + '); import unittest; unittest.main(module="test_model_reviewed_guidance", argv=["test", "ReviewedGuidanceTests.test_public_cli_official_path_drops_legacy_cache_and_retained_acceptance"])'
        with tempfile.TemporaryDirectory() as temporary:
            environment = {**os.environ, 'PYTHONPATH': os.environ.get('PYTHONPATH', '').split(os.pathsep)[0]}
            result = subprocess.run([sys.executable, '-c', bootstrap], cwd=temporary, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_public_cli_official_path_drops_legacy_cache_and_retained_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, cache = Path(temporary) / 'source.json', Path(temporary) / 'cache'
            source.write_text(json.dumps(self.evidence))
            legacy = self.cli('read', {'context': self.context}, source, cache)
            self.assertIn('Accept replacement', legacy['choices'])
            source.unlink()
            with self.subTest(seam='read'):
                draft = self.official_cli('read', {'context': self.context}, cache)
                self.assertNotIn('Accept replacement', draft['choices'])
                self.assertEqual(draft['recommendation_evidence']['guidance'], [])
                self.assertIn('No reviewed guidance yet for fixture-analysis, fixture-code', draft['recommendations']['implementation']['rationale'])
            with self.subTest(seam='retained Accept'):
                accepted = self.official_cli('reply', {'proposal': legacy, 'reply': 'Accept replacement'}, cache)
                self.assertEqual(accepted['after'], legacy['after'])
                self.assertNotIn('Accept replacement', accepted['choices'])
                self.assertIsNone(accepted['recommendations']['implementation']['choice'])
            with self.subTest(seam='CLI error recovery'):
                error = self.official_cli('reply', {'proposal': legacy}, cache, expected_code=2)
                retained = error['retained_proposal']
                self.assertEqual(retained['after'], legacy['after'])
                self.assertIsNone(retained['recommendations']['implementation']['choice'])
                self.assertNotIn('Accept replacement', retained['choices'])
            self.assertEqual(self.state.read_bytes(), self.original)
            self.assertFalse((self.project / '.playbook-config.json').exists())

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

    def test_edition_list_is_valid_and_holds_only_the_reviewed_entry(self):
        entries = load_reviewed_guidance()
        self.assertEqual([(entry['model_id'], entry['tasks'], entry['source_url']) for entry in entries],
                         [('gpt-6-astra', ['coding'], SOURCES[0])])
        self.assertEqual(entries[0]['heading'], 'Choosing a model')
        self.assertIn('use GPT-6 Astra, our flagship model for complex reasoning and coding.', entries[0]['paragraph'])

    def test_malformed_lists_fail_closed(self):
        broken = []
        for key in ENTRY:
            missing = dict(ENTRY)
            del missing[key]
            broken.append([missing] if key != 'label' else None)
        for key, value in (('model_id', 'Fixture Code'), ('provider', 'other'), ('tasks', []), ('tasks', ['cooking']),
                           ('risks', ['high']), ('source_url', SOURCES[2]), ('source_url', SOURCES[3]), ('heading', ' '),
                           ('paragraph', ''), ('link', '/elsewhere'), ('reviewed_at', 'yesterday'), ('extra', 'x')):
            broken.append([{**ENTRY, key: value}])
        broken += [[ENTRY, ENTRY], 'not a list', [{**ENTRY, 'provider': 'anthropic', 'source_url': SOURCES[3]}]]
        for entries in filter(None, broken):
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    validate_reviewed_guidance(entries)
                evidence = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: PAGE, reviewed=entries).retrieve(urls=[SOURCES[0]])
                self.assertEqual(evidence['guidance'], [])
                self.assertIn('reviewed guidance list is invalid', evidence['sources'][0]['uncertainty'])
        validate_reviewed_guidance([{**ENTRY, 'model_id': 'claude-fixture-1-0', 'provider': 'anthropic', 'label': 'Claude Fixture 1.0',
                                     'source_url': SOURCES[3], 'link': '/docs/en/about-claude/models/overview'}])

    def test_confirmed_entry_supplies_dated_guidance_and_draft_only_replacement(self):
        variants = (PAGE, PAGE.replace('<p>', '<p>\n  ').replace(', our', ',\n our'),
                    PAGE.replace('flagship', '<strong>flagship</strong>').replace('<h2>', '<h2><span>').replace('</h2>', '</span></h2>'))
        for page in variants:
            with self.subTest(page=page):
                evidence = self.retrieve(page)
                self.assertEqual(len(evidence['guidance']), 1)
                record = evidence['guidance'][0]
                self.assertEqual((record['model_id'], record['provider'], record['tasks'], record['risks'], record['label']),
                                 ('fixture-code', 'openai', ['coding'], ['ordinary', 'high'], 'Fixture Code'))
                self.assertEqual((record['source_url'], record['checked_at'], record['reviewed_at'], record['text']),
                                 (SOURCES[0], fixtures.NOW, '2026-10-05', PARAGRAPH))
                self.assertIn('reviewed', record['uncertainty'])
                self.assertEqual(evidence['sources'][0]['status'], 'retrieved')
                service = self.service(sources=lambda: evidence)
                draft = service.read()
                self.assertIn('Accept replacement', draft['choices'])
                accepted = service.reply(draft, 'Accept replacement')
                role = draft['replacement']['role']
                self.assertEqual(accepted['step'], 'preview')
                self.assertEqual(accepted['after'][role]['model_id'], 'fixture-code')
                self.assertTrue(all(accepted['after'][other] == draft['after'][other] for other in ROLES if other != role))
                self.assertFalse(accepted['launched'])
                self.assertEqual(service.reply(accepted, 'Not now')['state'], 'unchanged')
                self.assertEqual(self.state.read_bytes(), self.original)
                self.assertFalse((self.project / '.playbook-config.json').exists())

    def test_any_change_to_the_reviewed_context_withdraws_the_entry(self):
        paragraph = '<p>' + LINKED + '</p>'
        for page in (
            PAGE.replace('<p>If', '<p>If enabled, if'),
            PAGE.replace('cost.</p>', 'cost. It does not support coding.</p>', 1),
            PAGE.replace('Choosing a model', 'Choosing a preview model'),
            PAGE.replace('/api/docs/models/fixture-code', '/api/docs/models/fixture-other'),
            PAGE.replace('<a href="/api/docs/models/fixture-code">Fixture Code</a>', 'Fixture Code'),
            PAGE.replace(paragraph, '<p>If enabled:</p>' + paragraph),
            PAGE.replace('cost.</p>', 'cost.<span><div>Only while access remains enabled.</div></span></p>', 1),
            PAGE.replace('</p><p>All', '<div>Only while access remains enabled.</div></p><p>All', 1),
            PAGE.replace('<h2>', '<h2>Retired: '),
            PAGE.replace(paragraph, '<del>' + paragraph + '</del>'),
            PAGE.replace(paragraph, '<p><s>' + LINKED + '</s></p>'),
            PAGE.replace(paragraph, '<p><strike>' + LINKED + '</strike></p>'),
            PAGE.replace(paragraph, '<blockquote cite="https://outside.example">' + paragraph + '</blockquote>'),
            PAGE.replace(paragraph, '<p><q>' + LINKED + '</q></p>'),
            PAGE.replace('<h2>' + HEADING + '</h2>', '<h2><del>' + HEADING + '</del></h2>'),
            PAGE.replace('<h2>' + HEADING + '</h2>', ''),
            '<main><p>' + LINKED + '</p></main>',
        ):
            with self.subTest(page=page):
                self.assert_withdrawn(page)

    def test_entries_are_confirmed_only_on_their_own_official_source(self):
        evidence = self.retrieve(PAGE, url=SOURCES[3])
        self.assertEqual(evidence['guidance'], [])
        self.assertEqual(evidence['sources'][0]['status'], 'incomplete')

    def test_unreviewed_prose_never_supplies_task_fit(self):
        for page in (
            '<p><a href="/api/docs/models/fixture-code">Fixture Code</a> Suitable for coding.</p>',
            '<p>Use <a href="/api/docs/models/fixture-code">Fixture Code</a> for complex reasoning and coding.</p>',
            '<a href="/api/docs/models/fixture-code"><div>Fixture Code</div><div>Our flagship model for complex coding.</div></a>',
            '<p>Claude Fixture 1.0 (claude-fixture-1-0) is built for complex coding.</p>',
        ):
            for url in (SOURCES[0], SOURCES[3]):
                with self.subTest(page=page, url=url):
                    self.assertEqual(self.retrieve(page, entries=(), url=url)['guidance'], [])

    def test_models_without_reviewed_guidance_are_named(self):
        self.evidence['guidance'] = [record for record in self.evidence['guidance'] if record['model_id'] == 'fixture-analysis']
        draft = self.service().read()
        advice = draft['recommendations']['implementation']
        self.assertIsNone(advice['choice'])
        self.assertIn('No reviewed guidance yet for fixture-code', advice['rationale'])

    def test_withdrawal_is_reported_as_a_material_change(self):
        from model_evidence_cache import EvidenceCache
        pages = {'page': PAGE}
        sources = OfficialSources(lambda: fixtures.NOW, fetch=lambda url: pages['page'] if url == SOURCES[0] else '<p>Unknown</p>',
                                  reviewed=[ENTRY])
        cache = EvidenceCache(lambda: fixtures.NOW)
        discovery = {'revision': 'fixture', 'routes': deepcopy(self.routes)}
        first = cache.retrieve(sources.retrieve, discovery)
        self.assertEqual([record['model_id'] for record in first['guidance']], ['fixture-code'])
        pages['page'] = PAGE.replace('<p>If', '<p>If enabled, if')
        second = cache.retrieve(sources.retrieve, discovery, force=True)
        self.assertEqual(second['guidance'], [])
        self.assertEqual([change['source_url'] for change in second['changes']], [SOURCES[0]])

    def test_release_check_reports_confirmation_and_withdrawal(self):
        script = Path(__file__).with_name('check-model-guidance.py')
        with tempfile.TemporaryDirectory() as temporary:
            listing = Path(temporary) / 'guidance.json'
            listing.write_text(json.dumps({'schema_version': 1, 'entries': [ENTRY]}))
            page = Path(temporary) / 'page.html'
            for html, code, word in ((PAGE, 0, 'confirmed'), (PAGE.replace('<p>If', '<p>If enabled, if'), 1, WITHDRAWN)):
                page.write_text(html)
                result = subprocess.run([sys.executable, str(script), '--guidance', str(listing), '--page', SOURCES[0] + '=' + str(page)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertIn(word, result.stdout)
                self.assertIn('fixture-code', result.stdout)
            listing.write_text('{"schema_version": 1, "entries": [{}]}')
            result = subprocess.run([sys.executable, str(script), '--guidance', str(listing), '--page', SOURCES[0] + '=' + str(page)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
