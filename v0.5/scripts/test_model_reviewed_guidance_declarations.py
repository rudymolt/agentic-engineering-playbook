"""Reviewed guidance declaration and parsing contracts."""
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
