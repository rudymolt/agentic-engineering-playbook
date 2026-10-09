"""Reviewed guidance rendering boundaries."""
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


from reviewed_guidance_support import (ReviewedGuidanceCase, HEADING, PARAGRAPH, ENTRY, LINKED, PAGE, WITHDRAWN, RUBY_ENTRY, RUBY_PAGE)


class ReviewedGuidanceTests(ReviewedGuidanceCase):
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
