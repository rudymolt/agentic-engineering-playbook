"""Reviewed guidance source, cache, and CLI contracts."""
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
        with patch.dict(ENTRY, entry), patch('reviewed_guidance_support.PAGE', positive):
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
