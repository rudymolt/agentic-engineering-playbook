"""Read-only official evidence and bounded advice; never a selection authority."""

from copy import deepcopy
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import math
import hashlib
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


SOURCES = (
    "https://developers.openai.com/api/docs/models",
    "https://developers.openai.com/api/docs/guides/reasoning",
    "https://developers.openai.com/api/docs/pricing",
    "https://platform.claude.com/docs/en/about-claude/models/choosing-a-model",
    "https://platform.claude.com/docs/en/about-claude/pricing",
)
LIMITATIONS = "Provider guidance is not account availability or project verification. No benchmark, savings guarantee or cheapest verified outcome claim. Existing authority, permissions, independence, repair ceilings and feature gates still apply."


REVIEWED_GUIDANCE = Path(__file__).resolve().parent.parent / "model-guidance.json"
GUIDANCE_KEYS = {"model_id", "provider", "label", "tasks", "risks", "source_url", "heading", "paragraph", "link", "reviewed_at"}
GUIDANCE_SOURCES = {"openai": SOURCES[0], "anthropic": SOURCES[3]}
# Markup that removes, strikes or quotes text never confirms a provider statement.
UNASSERTED = frozenset({"del", "s", "strike", "blockquote", "q"})
WITHDRAWN = "provider wording changed since review"
# Unicode Default_Ignorable_Code_Point, including combining marks, fillers,
# variation selectors and reserved invisible ranges as well as format controls.
DEFAULT_IGNORABLE_RANGES = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160),
                           (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E),
                           (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
                           (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
                           (0xE0000, 0xE0FFF))


# Immutable Unicode lookup only; never reviewed-guidance or authority data.
_DEFAULT_IGNORABLE_CHARACTERS = frozenset(chr(point) for start, end in DEFAULT_IGNORABLE_RANGES
                                        for point in range(start, end + 1))


def validate_reviewed_guidance(entries):
    """Return reviewed entries unchanged, or raise ValueError for any malformed entry."""
    if not isinstance(entries, list):
        raise ValueError("Reviewed guidance must be a list of entries.")
    seen, labels = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != GUIDANCE_KEYS:
            raise ValueError("Reviewed guidance entries require exactly: " + ", ".join(sorted(GUIDANCE_KEYS)))
        if (not isinstance(entry["model_id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", entry["model_id"])
                or GUIDANCE_SOURCES.get(entry["provider"]) != entry["source_url"]
                or not isinstance(entry["tasks"], list) or not entry["tasks"] or not set(entry["tasks"]) <= {"coding", "analysis"}
                or not isinstance(entry["risks"], list) or "ordinary" not in entry["risks"] or not set(entry["risks"]) <= {"ordinary", "high"}
                or any(not isinstance(entry[key], str) or not rendered_text([entry[key]]) for key in ("label", "heading", "paragraph"))
                or not isinstance(entry["link"], str) or not entry["link"].startswith("/")
                or entry["provider"] == "openai" and entry["link"] != "/api/docs/models/" + entry["model_id"]
                or entry["provider"] == "anthropic" and not entry["link"].startswith("/docs/")
                or not isinstance(entry["reviewed_at"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["reviewed_at"])
                or (entry["model_id"], entry["source_url"]) in seen
                or (entry["provider"], rendered_text([entry["label"]])) in labels):
            raise ValueError("Invalid reviewed guidance entry for " + repr(entry.get("model_id")))
        datetime.strptime(entry["reviewed_at"], "%Y-%m-%d")
        seen.add((entry["model_id"], entry["source_url"]))
        labels.add((entry["provider"], rendered_text([entry["label"]])))
    return entries


def load_reviewed_guidance(path=REVIEWED_GUIDANCE):
    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate reviewed guidance key: " + key)
            value[key] = item
        return value
    data = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    if (not isinstance(data, dict) or set(data) != {"schema_version", "entries"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1):
        raise ValueError("Unsupported reviewed guidance file.")
    return validate_reviewed_guidance(data["entries"])


def rendered_text(parts):
    # Remove invisible code points before normalising the composed visible text.
    text = unicodedata.normalize("NFKC", "".join(ch for ch in "".join(parts)
                                  if ch not in _DEFAULT_IGNORABLE_CHARACTERS))
    return re.sub(r"\s+", " ", text).strip()


def entry_fingerprint(entry):
    """Bind confirmation to every field of the complete reviewed entry."""
    return hashlib.sha256(json.dumps(entry, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def matches_reviewed_guidance(record, entries):
    """Only the exact reviewed claim can reuse an official confirmation."""
    if not isinstance(record, dict):
        return False
    return any(record.get('entry_fingerprint') == entry_fingerprint(entry)
               and all(record.get(key) == entry[key] for key in
                   ("model_id", "provider", "label", "tasks", "risks", "source_url", "reviewed_at"))
               and record.get("text") == rendered_text([entry["paragraph"]]) for entry in entries)


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if urlparse(newurl).scheme != "https" or urlparse(newurl).hostname != urlparse(request.full_url).hostname:
            raise URLError("Nonofficial redirect blocked")
        return super().redirect_request(request, response, code, message, headers, newurl)


def valid_rate_number(value):
    return type(value) in (int, float) and 0 <= value <= 2 ** 53 - 1 and math.isfinite(value)


def base_pricing_context(text):
    normalized = re.sub(r"[\s\-\u2010-\u2015]+", " ", text).strip().lower()
    return normalized in {"", "model pricing", "standard", "base api pricing", "standard base pricing",
                          "short context", "short context only", "short context rates", "short context pricing"}


VOID = frozenset({"area", "base", "basefont", "bgsound", "br", "col", "embed", "hr", "img", "input", "keygen", "link", "meta", "param", "source", "track", "wbr"})
RAW_TEXT = frozenset({"script", "style", "xmp", "iframe", "noembed", "noframes", "noscript", "textarea", "title", "plaintext"})
NONRENDERED = frozenset({"area", "base", "basefont", "bgsound", "datalist", "link", "meta", "param", "source", "track"})
SCRIPT_TRANSITIONS = re.compile(r"<!--|-->|<script(?=[\t\n\r\f />])", re.IGNORECASE | re.ASCII)
INLINE = frozenset({"a", "abbr", "b", "bdi", "bdo", "big", "br", "cite", "code", "data", "dfn", "em", "font", "i", "img", "kbd",
                    "mark", "nobr", "q", "rb", "rp", "rt", "rtc", "ruby", "s", "samp", "small", "span", "strike", "strong", "sub", "sup", "time", "tt", "u", "var", "wbr", "del", "ins"})
PARAGRAPH_BREAKS = frozenset({"address", "article", "aside", "blockquote", "center", "details", "dialog", "dir", "div", "dl", "fieldset",
                             "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
                             "hgroup", "hr", "li", "dd", "dt", "listing", "main", "menu", "nav", "ol", "p", "plaintext",
                             "pre", "search", "section", "summary", "table", "ul", "xmp"})
HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
SCOPE_BOUNDARIES = frozenset({"applet", "button", "caption", "html", "marquee", "object", "table", "td", "th", "template"})
FOREIGN = frozenset({"svg", "math"})
FOREIGN_INTEGRATION = frozenset({"foreignobject", "desc", "title", "mi", "mo", "mn", "ms", "mtext", "annotation-xml"})
FOREIGN_BREAKOUT = frozenset({"b", "big", "blockquote", "body", "br", "center", "code", "dd", "div", "dl", "dt", "em",
                             "embed", "font", "head", "hr", "i", "img", "li", "listing", "menu", "meta", "nobr", "ol",
                             "p", "pre", "ruby", "s", "small", "span", "strong", "strike", "sub", "sup", "table", "tt", "u", "ul", "var"}) | HEADINGS
CONTENT_SCOPES = FOREIGN | {"select", "option", "optgroup", "button", "meter", "progress", "object", "applet",
                            "audio", "video", "canvas", "frameset"}
TABLE_STRUCTURE = frozenset({"caption", "colgroup", "thead", "tbody", "tfoot", "tr", "td", "th"})
FORMATTING = frozenset({"a", "b", "big", "code", "em", "font", "i", "nobr", "s", "small", "strike", "strong", "tt", "u"})
FORMATTING_MARKERS = frozenset({"td", "th", "caption", "marquee"})
SCOPED_ENDS = PARAGRAPH_BREAKS | HEADINGS | {"applet", "button", "marquee", "object"}
SPECIAL = SCOPED_ENDS | TABLE_STRUCTURE | RAW_TEXT | NONRENDERED | {
    "basefont", "bgsound", "body", "br", "embed", "frame", "frameset", "head", "html", "img", "input",
    "keygen", "select", "template", "wbr"}


class Node:
    """Minimal element tree: reviewed text is located by heading and block, not by prose."""

    __slots__ = ("tag", "parent", "href", "children", "_block", "ambiguous", "forbidden_descendant")

    def __init__(self, tag, parent, href=None, ambiguous=False):
        self.tag, self.parent, self.href, self.children, self._block = tag, parent, href, [], None
        self.ambiguous = ambiguous
        self.forbidden_descendant = False

    def elements(self):
        pending = [iter(self.children)]
        while pending:
            child = next(pending[-1], None)
            if child is None:
                pending.pop()
                continue
            if isinstance(child, Node):
                yield child
                pending.append(iter(child.children))

    def block(self):
        pending = [(self, False)]
        while pending:
            node, visited = pending.pop()
            if node._block is not None:
                continue
            if node.tag not in INLINE:
                node._block = True
            elif visited:
                node._block = any(child._block for child in node.children if isinstance(child, Node))
            else:
                pending.append((node, True))
                pending.extend((child, False) for child in node.children if isinstance(child, Node))
        return self._block

    def render(self, own=False):
        """Rendered text; `own` excludes nested blocks so a block cannot borrow a child's text."""
        return rendered_text([self.raw_text(own)])

    def raw_text(self, own=False):
        """Compose inline text before normalising whitespace at the block boundary."""
        parts = []
        pending = [iter(self.children)]
        while pending:
            child = next(pending[-1], None)
            if child is None:
                pending.pop()
                continue
            if isinstance(child, str):
                parts.append(child)
            elif child.tag == "br":
                parts.append(" ")
            elif child.block():
                parts.append(" ")
                if not own:
                    # A trailing separator belongs after this child's subtree.
                    pending.append(iter((" ",)))
                    pending.append(iter(child.children))
            else:
                pending.append(iter(child.children))
        return "".join(parts)

    def asserted(self):
        if self.forbidden_descendant:
            return False
        node = self
        table_content = False
        while node is not None:
            if node.tag in UNASSERTED or node.ambiguous:
                return False
            if node.tag in {"td", "th", "caption"}:
                table_content = True
            if node.tag == "table":
                # Outside cells/captions, HTML can relocate content around a
                # table. Withdraw rather than reconstruct that browser tree.
                if not table_content:
                    return False
                table_content = False
            node = node.parent
        return not any(node.tag in UNASSERTED or node.ambiguous or node.forbidden_descendant for node in self.elements())


def page_units(root):
    """Headings and blocks in document order, including empty leaf blocks."""
    units = []
    pending = [root]
    while pending:
        node = pending.pop()
        if re.fullmatch(r"h[1-6]", node.tag):
            units.append(node)
            continue
        if node.block() and (node.render(own=True) or not any(child.block() for child in node.elements())):
            units.append(node)
        pending.extend(child for child in reversed(node.children) if isinstance(child, Node) and child.block())
    return units


def confirms(entry, units):
    """The reviewed heading is immediately followed by a leaf block holding exactly the reviewed paragraph and model link."""
    heading, paragraph = rendered_text([entry["heading"]]), rendered_text([entry["paragraph"]])
    for index, unit in enumerate(units[:-1]):
        block = units[index + 1]
        if (re.fullmatch(r"h[1-6]", unit.tag) and unit.render() == heading and unit.asserted()
                and not re.fullmatch(r"h[1-6]", block.tag) and block.asserted()
                and not any(node.block() for node in block.elements()) and block.render() == paragraph
                and any(node.tag == "a" and node.href == entry["link"] for node in block.elements())):
            return True
    return False


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = []
        self.declaration_scope = []
        self.content_scope = []
        self.integration = []
        self.foreign_breakout = set()
        self.document_seen = set()
        self.visibility = []
        self.formatting = []
        self.script_state = "data"
        self.text = []
        self.root = Node("#root", None)
        self.node = self.root
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.elements = []
        self.heading = None
        self.heading_text = ""
        self.heading_end = 0
        self.heading_scope = []
        self.caption = None

    def close(self):
        # feed has consumed complete tokens. At native EOF, bare < and </
        # become text, and buffered character references resolve. Truncated
        # tags/comments/declarations are discarded, not flushed as text.
        # Keep raw/RCDATA bodies withheld and use the existing visibility
        # gates for hidden, inert and foreign descendants.
        tail, self.rawdata = self.rawdata, ""
        if tail and not self.cdata_elem and (not tail.startswith("<") or tail in {"<", "</"}):
            self.handle_data(unescape(tail))

    def parse_html_declaration(self, index):
        # In native HTML, even uppercase CDATA/SGML marked openers are bogus
        # comments ending at the first >. The inherited CDATA path consumes
        # through ]]>, erasing visible text after that first boundary.
        # Withholding is not a namespace: native template declarations still
        # end at >, while actual foreign CDATA consumes close-like text.
        foreign = bool(self.declaration_scope and self.declaration_scope[-1][1] in FOREIGN)
        if (self.rawdata.startswith('<![', index)
                and not (foreign and self.rawdata.startswith('<![CDATA[', index))):
            return self.parse_bogus_comment(index)
        return super().parse_html_declaration(index)

    def declaration_start(self, tag, attrs):
        # Track only declaration namespaces inside foreign/inert scopes.
        # This does not collect rendered nodes or release visibility barriers.
        namespace = "html"
        if self.declaration_scope:
            parent, namespace, integration = self.declaration_scope[-1]
            for index in range(len(self.declaration_scope) - 1, -1, -1):
                current, current_namespace, _ = self.declaration_scope[index]
                if current_namespace != "html" or current == "template":
                    break
                if current == "select":
                    if tag not in {"option", "optgroup", "select", "script", "template", "textarea", "input", "keygen"}:
                        return False
                    if tag in {"select", "textarea", "input", "keygen"}:
                        del self.declaration_scope[index:]
                        if tag == "select":
                            return True
                    break
            if (integration and (parent not in {"mi", "mo", "mn", "ms", "mtext"}
                                 or tag not in {"mglyph", "malignmark"})
                    or namespace == "math" and parent == "annotation-xml" and tag == "svg"):
                namespace = "html"
            if namespace in FOREIGN and (tag in FOREIGN_BREAKOUT - {"font"}
                    or tag == "font" and any(name in {"color", "face", "size"} for name, _ in attrs)):
                while self.declaration_scope and self.declaration_scope[-1][1] in FOREIGN and not self.declaration_scope[-1][2]:
                    self.declaration_scope.pop()
                namespace = "html"
        if namespace == "html" and tag in FOREIGN:
            namespace = tag
        encoding = next((value for name, value in attrs if name == "encoding"), None) or ""
        integration = (namespace == "svg" and tag in {"foreignobject", "desc", "title"}
                       or namespace == "math" and (tag in {"mi", "mo", "mn", "ms", "mtext"}
                       or tag == "annotation-xml" and encoding.lower() in {"text/html", "application/xhtml+xml"}))
        if (self.declaration_scope or tag in CONTENT_SCOPES or tag == "template") and not (namespace == "html" and tag in VOID):
            self.declaration_scope.append((tag, namespace, integration))
        return True

    def declaration_end(self, tag):
        for index in range(len(self.declaration_scope) - 1, -1, -1):
            current, namespace, _ = self.declaration_scope[index]
            if namespace != "html" or current in RAW_TEXT | {"template"}:
                break
            if current == "select":
                # Native select ignores unrelated ends, including foreign
                # integration ancestors. They cannot change CDATA context.
                if tag == "select":
                    del self.declaration_scope[index:]
                    return True
                if tag == "option" and self.declaration_scope[-1][0] == "option":
                    self.declaration_scope.pop()
                    return True
                if tag == "optgroup":
                    if (len(self.declaration_scope) > index + 2 and self.declaration_scope[-1][0] == "option"
                            and self.declaration_scope[-2][0] == "optgroup"):
                        self.declaration_scope.pop()
                    if self.declaration_scope[-1][0] == "optgroup":
                        self.declaration_scope.pop()
                        return True
                if tag != "template":
                    return False
                break
        if tag in {"br", "p"}:
            # These foreign end tokens break out to native HTML processing.
            while self.declaration_scope and self.declaration_scope[-1][1] in FOREIGN and not self.declaration_scope[-1][2]:
                self.declaration_scope.pop()
        for index in range(len(self.declaration_scope) - 1, -1, -1):
            current, namespace, _ = self.declaration_scope[index]
            if current == tag:
                del self.declaration_scope[index:]
                return namespace == "html"
            if namespace == "html" and current in RAW_TEXT | {"template"}:
                return False
        return not self.declaration_scope

    def parse_comment(self, index, report=True):
        # An abrupt empty close takes precedence over any later full close.
        # HTMLParser searches for a full close first, swallowing visible text
        # between repeated abrupt comments or a subsequent ordinary comment.
        for token in ('<!-->', '<!--->'):
            if self.rawdata.startswith(token, index):
                if report:
                    self.handle_comment('')
                return index + len(token)
        return super().parse_comment(index, report)

    def parse_endtag(self, index):
        # In HTML script double-escaped text, </script merely returns to
        # escaped text. HTMLParser otherwise treats every such token as a close.
        if self.cdata_elem == "script" and self.script_state == "double":
            self.script_state = "escaped"
            return index + len("</script")
        return super().parse_endtag(index)

    def parse_starttag(self, index):
        # HTMLParser may enter a raw mode after our callback, with different
        # built-in families on supported Pythons. Ignored native tokens and
        # foreign integration-point names must not enter that mode.
        self.ignore_literal_start = False
        end = super().parse_starttag(index)
        if self.ignore_literal_start:
            self.clear_cdata_mode()
        return end

    def handle_starttag(self, tag, attrs):
        if not self.declaration_start(tag, attrs):
            self.ignore_literal_start = True
            return
        if tag == "image" and not self.skip and not self.content_scope:
            # The legacy HTML alias is img, not a hidden ancestor for following
            # text. Foreign/integration and raw/inert scopes stay withheld.
            tag = "img"
        foreign = bool(self.content_scope and self.content_scope[-1] in FOREIGN)
        if (foreign and not self.skip and tag in FOREIGN_BREAKOUT
                and not any(level == len(self.content_scope) for _, level in self.integration)):
            # HTML breakout tokens make later self-closing flags ambiguous.
            # Keep withholding this subtree, with HTML raw/inert safeguards.
            self.foreign_breakout.add(len(self.content_scope))
        integration = foreign and len(self.content_scope) not in self.foreign_breakout and tag in FOREIGN_INTEGRATION
        if not self.skip and not self.content_scope:
            if self.visibility and self.visibility[-1]["tag"] == "head" and tag not in {
                    "base", "basefont", "bgsound", "link", "meta", "title", "noscript", "noframes", "style", "script", "template"}:
                self.handle_endtag("head")
            # Preserve bounded implied ends before excluding nonrendered tags.
            # Use the full visibility stack: hidden p/li/cells also end here.
            if tag in PARAGRAPH_BREAKS:
                self.close_implied({"p"}, SCOPE_BOUNDARIES, ambiguous=tag != "p")
            if tag in HEADINGS:
                self.close_implied(HEADINGS, SCOPE_BOUNDARIES)
            if tag == "li":
                self.close_implied({"li"}, SCOPE_BOUNDARIES | {"ul", "ol", "menu"})
            if tag in {"dt", "dd"}:
                self.close_implied({"dt", "dd"}, SCOPE_BOUNDARIES | {"dl"})
            if tag in TABLE_STRUCTURE:
                self.close_implied({"caption", "colgroup"}, {"table"})
            if tag in {"td", "th", "tr", "thead", "tbody", "tfoot", "caption", "colgroup"}:
                self.close_implied({"td", "th"}, {"table"})
            if tag in {"tr", "thead", "tbody", "tfoot", "caption", "colgroup"}:
                self.close_implied({"tr"}, {"table"})
            if tag in {"thead", "tbody", "tfoot", "caption", "colgroup"}:
                self.close_implied({"thead", "tbody", "tfoot"}, {"table"})
            if tag in {"rb", "rp", "rt", "rtc"}:
                for scope in reversed(self.visibility):
                    if scope["tag"] == "ruby":
                        # Ruby starts generate implied ends only at the top
                        # of the stack. rt/rp retain an enclosing rtc; hidden
                        # annotation state must end before the new start.
                        implied = {"dd", "dt", "li", "optgroup", "option", "p", "rb", "rp", "rt", "rtc"}
                        if tag in {"rt", "rp"}:
                            implied.remove("rtc")
                        while self.visibility and self.visibility[-1]["tag"] in implied:
                            self.handle_endtag(self.visibility[-1]["tag"])
                        break
                    if scope["tag"] in SCOPE_BOUNDARIES:
                        break
            if tag == "frame":
                # Outside a frameset this native start is ignored. Its hidden
                # attribute cannot turn following text into a hidden subtree.
                return
        foreign_literal_name = (foreign and len(self.content_scope) not in self.foreign_breakout
                                and not any(level == len(self.content_scope) for _, level in self.integration)
                                and tag not in {"script", "style"})
        native_declaration = not (self.declaration_scope and self.declaration_scope[-1][1] in FOREIGN)
        raw = (native_declaration and tag in RAW_TEXT and (bool(self.skip) or not integration and not foreign_literal_name
               and not (self.content_scope and self.content_scope[-1] == "select" and tag not in {"script", "textarea"})))
        if tag in RAW_TEXT and not raw:
            self.ignore_literal_start = True
        if raw:
            # Consume literal bodies, including apparent nested tags/end tags.
            # HTMLParser's built-in family differs between supported Pythons;
            # self-closing syntax also needs to enter this mode explicitly.
            self.set_cdata_mode(tag)
            if tag == "script":
                self.script_state = "data"
            if tag == "plaintext":
                self.interesting = re.compile(r"(?!)")  # No closing tag in HTML.
        if raw or tag == "template" and native_declaration:
            self.skip.append(tag)
        if self.skip:
            return
        if self.content_scope:
            if integration:
                self.integration.append((tag, len(self.content_scope)))
            if tag in CONTENT_SCOPES and (self.content_scope[-1] != "select"
                                         or tag == self.content_scope[-1]):
                self.content_scope.append(tag)
            return
        misplaced_document = (tag in {"html", "head", "body"}
                              and (tag in self.document_seen or any(scope["tag"] != "html" for scope in self.visibility)))
        if tag in {"html", "head", "body"}:
            self.document_seen.add(tag)
        ignored_table = tag in TABLE_STRUCTURE and not any(scope["tag"] == "table" for scope in self.visibility)
        nested_form = tag == "form" and any(scope["tag"] == "form" for scope in self.visibility)
        if tag in CONTENT_SCOPES or misplaced_document or ignored_table or nested_form:
            # Native content models can ignore apparent headings and links.
            # Keep a barrier, then withhold the scope rather than simulate its
            # insertion mode. Nested starts and unrelated closes cannot escape.
            self.content_scope.append(tag)
            if misplaced_document and tag in {"html", "body"}:
                # Repeated document tokens can merge attributes onto the real
                # document instead of opening this apparent hidden element.
                self.root.ambiguous = True
                self.tables.clear()
            # Literal visibility cannot prove any ambiguous scope, including
            # ignored table/document starts and nested forms. Their tokens can
            # expose qualifiers outside an apparent hidden/closed ancestor.
            self.node.children.append(Node(tag, self.node, ambiguous=True))
            self.text.append("Unknown content")
            for collector in (self.heading, self.caption, self.cell):
                if collector is not None:
                    collector.append("Unknown content")
            return
        attributes = dict(attrs)
        if tag in {"a", "nobr"}:
            for scope in reversed(self.formatting):
                if scope["tag"] in FORMATTING_MARKERS:
                    break
                if scope["tag"] == tag:
                    # These starts can adopt/close an earlier formatting
                    # element, exposing text outside its apparent hidden scope.
                    self.mark_formatting_ambiguous()
                    break
        # Keep nonrendered scope out of both the reviewed tree and pricing
        # collectors. Presence controls boolean attributes, whatever the value.
        parent = self.visibility[-1] if self.visibility else None
        summary = bool(parent and parent["tag"] == "details" and tag == "summary" and not parent["summary_seen"])
        if parent and parent["tag"] == "details" and tag == "summary":
            parent["summary_seen"] = True
        hidden = ("hidden" in attributes or tag == "dialog" and "open" not in attributes
                  or tag in NONRENDERED
                  or tag == "input" and (next((value for name, value in attrs if name == "type"), "") or "").lower() == "hidden"
                  or bool(parent and (parent["hidden"] or parent["closed_details"] and not summary)))
        if tag not in VOID:
            self.visibility.append({"tag": tag, "hidden": hidden,
                                    "closed_details": tag == "details" and "open" not in attributes,
                                    "summary_seen": False, "detached": False})
            if tag in FORMATTING | FORMATTING_MARKERS:
                self.formatting.append(self.visibility[-1])
        if hidden:
            # Visibility removes text, links and blocks, but not the separate
            # forbidden-descendant condition. Retain it on the containing
            # visible node without adding hidden adjacency or leaf evidence.
            # Raw bodies, inert templates and withheld content returned above.
            if tag in UNASSERTED:
                self.node.forbidden_descendant = True
            return
        # Inline starts can reconstruct formatting immediately. Structural
        # wrappers must not poison visible units after a later own close;
        # affected character data retains its own ambiguity below.
        node = Node(tag, self.node, attributes.get("href"),
                    len(attributes) != len(attrs) or tag in INLINE and self.formatting_ambiguous())
        self.node.children.append(node)
        if tag not in VOID:
            self.node = node
            self.elements.append((tag, attributes, len(self.text)))
        if re.fullmatch(r"h[1-6]", tag):
            self.heading = []
            self.heading_scope = list(self.elements[:-1])
        if tag == "caption":
            self.caption = []
        if tag == "table":
            panes = [(attributes.get("data-value"), start) for _, attributes, start in self.elements
                     if attributes.get("data-content-switcher-pane") == "true"]
            tier = panes[-1][0] if panes else self.heading_text.lower()
            context_start = panes[-1][1] if panes else self.heading_end
            if not panes and self.elements[:len(self.heading_scope)] != self.heading_scope:
                tier = "unknown"
            if panes and self.heading_end > context_start and self.heading_text.lower() not in {"standard", "short context"}:
                tier = "unknown"
            self.table = {"prefix": " ".join(self.text)[-2500:], "rows": [],
                          "tier": tier, "tier_context": " ".join(self.text[context_start:]),
                          "caption": ""}
        if tag == "tr" and self.table is not None:
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = []
        if tag in {"p", "div", "tr", "h1", "h2", "h3"}:
            self.text.append("\n")

    def close_implied(self, tags, boundaries, ambiguous=False):
        for scope in reversed(self.visibility):
            if scope["tag"] in tags:
                if not scope["hidden"]:
                    node = self.node
                    while node is not self.root and node.tag != scope["tag"]:
                        if node.tag == "p":
                            node.ambiguous = True
                        node = node.parent
                    if ambiguous and node is not self.root:
                        # An interrupted source paragraph cannot shed a nested
                        # block and become a newly trusted leaf paragraph.
                        node.ambiguous = True
                self.handle_endtag(scope["tag"])
                return
            if scope["tag"] in boundaries:
                return

    def formatting_ambiguous(self):
        return any(scope["detached"] for scope in self.formatting)

    def mark_formatting_ambiguous(self):
        self.node.children.append(Node("span", self.node, ambiguous=True))
        self.text.append("Unknown content")
        for collector in (self.heading, self.caption, self.cell):
            if collector is not None:
                collector.append("Unknown content")

    def handle_endtag(self, tag):
        native_end = self.declaration_end(tag)
        if self.skip:
            if native_end and tag == self.skip[-1]:
                self.skip.pop()
            return
        if self.content_scope:
            depth = len(self.content_scope)
            if self.integration and self.integration[-1] == (tag, depth):
                self.integration.pop()
            elif tag == self.content_scope[-1] and not any(level == depth for _, level in self.integration):
                self.content_scope.pop()
                self.foreign_breakout.discard(depth)
            return
        if tag == "br":
            # Native </br> is a br start with no attributes, not an
            # unmatched close. Keep the same rendered word separator.
            self.handle_starttag("br", [])
            return
        if tag in {"html", "body"}:
            # These ends change the document insertion mode, not ancestry.
            # Later tokens can still belong to the same hidden document.
            return
        if tag != "p":
            boundaries = SCOPE_BOUNDARIES if tag in SCOPED_ENDS | FORMATTING else SPECIAL
            if tag in TABLE_STRUCTURE | {"table"}:
                # Row/section/table ends may implicitly close cells, but an
                # unrelated ancestor end cannot cross the enclosing table.
                boundaries = {"html", "table", "template"}
            elif tag == "li":
                boundaries = boundaries | {"ol", "ul", "menu"}
            for scope in reversed(self.visibility):
                if scope["tag"] == tag:
                    if tag == "form" and scope is not self.visibility[-1]:
                        # Native form ends can remove only the form's stack
                        # entry; descendants retain their actual ancestry.
                        # Withhold misnesting instead of reconstructing it.
                        if not scope["hidden"]:
                            self.mark_formatting_ambiguous()
                        return
                    break
                if scope["tag"] in boundaries:
                    return
        if tag in {"tr", "thead", "tbody", "tfoot", "table"}:
            # Run native implied ends before removing ancestors so cell and
            # caption formatting markers also release visible successors.
            self.close_implied({"td", "th"}, {"table"})
            if tag != "tr":
                self.close_implied({"tr"}, {"table"})
            if tag == "table":
                self.close_implied({"caption", "colgroup", "thead", "tbody", "tfoot"}, {"table"})
        if tag in FORMATTING:
            for index in range(len(self.formatting) - 1, -1, -1):
                scope = self.formatting[index]
                if scope["tag"] in FORMATTING_MARKERS:
                    break
                if scope["tag"] == tag:
                    live = next((position for position, item in enumerate(self.visibility) if item is scope), None)
                    if live is not None and any(item["tag"] in SCOPE_BOUNDARIES for item in self.visibility[live + 1:]):
                        # An out-of-scope formatting close cannot release it.
                        break
                    if live is not None and live != len(self.visibility) - 1:
                        self.mark_formatting_ambiguous()
                        if any(item["tag"] not in INLINE for item in self.visibility[live + 1:]):
                            # Adoption across a furthest block can clone the
                            # formatting entry. Further own closes alone do
                            # not prove release without browser tree repair.
                            scope["adopted"] = True
                        node = self.node
                        while node is not self.root and node.tag != tag:
                            node = node.parent
                        if node is not self.root:
                            node.ambiguous = True
                    if not scope.get("adopted"):
                        self.formatting.pop(index)
                    break
        if tag == "p":
            paragraph_open = False
            for scope in reversed(self.visibility):
                if scope["tag"] == "p":
                    paragraph_open = True
                    break
                if scope["tag"] in SCOPE_BOUNDARIES:
                    break
            if not paragraph_open:
                # A stray </p> creates an empty HTML paragraph. Keep only a
                # fail-closed boundary, never borrow text or rebuild its tree.
                if not self.visibility or not (self.visibility[-1]["hidden"] or self.visibility[-1]["closed_details"]):
                    self.node.children.append(Node("p", self.node, ambiguous=True))
                    self.text.append("\n")
                return
        for index in range(len(self.visibility) - 1, -1, -1):
            if self.visibility[index]["tag"] == tag:
                hidden = self.visibility[index]["hidden"]
                # HTML retains unclosed active formatting across structural
                # ends and reconstructs it later. Keep an ambiguity barrier,
                # not a guessed browser tree or inherited visibility.
                for scope in self.visibility[index:]:
                    scope["detached"] = True
                if tag in FORMATTING_MARKERS:
                    for position in range(len(self.formatting) - 1, -1, -1):
                        if self.formatting[position] is self.visibility[index]:
                            del self.formatting[position:]
                            break
                del self.visibility[index:]
                if hidden:
                    return
                break
        else:
            if self.visibility and self.visibility[-1]["hidden"]:
                return
        for index in range(len(self.elements) - 1, -1, -1):
            if self.elements[index][0] == tag:
                del self.elements[index:]
                break
        node = self.node
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.node = node.parent
        if re.fullmatch(r"h[1-6]", tag) and self.heading is not None:
            self.heading_text = re.sub(r"[^a-zA-Z0-9 ]", "", " ".join(self.heading)).strip()
            self.heading_end = len(self.text)
            self.heading = None
        if tag in {"section", "article", "main"}:
            self.heading_text = ""
        if tag == "caption" and self.caption is not None and self.table is not None:
            self.table["caption"] = " ".join(self.caption)
            self.caption = None
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join(self.cell).strip())
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.table["rows"].append(self.row)
            self.row = None
        if tag == "table" and self.table is not None:
            if not self.root.ambiguous:
                self.tables.append(self.table)
            self.table = None
        if tag in {"p", "div", "section", "article", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table"}:
            self.text.append("\n")

    def handle_startendtag(self, tag, attrs):
        foreign = (not self.skip and tag != "template" and (tag in FOREIGN or bool(
                   self.content_scope and self.content_scope[-1] in FOREIGN
                   and len(self.content_scope) not in self.foreign_breakout
                   and not any(level == len(self.content_scope) for _, level in self.integration))))
        self.handle_starttag(tag, attrs)
        declaration_foreign = bool(self.declaration_scope and self.declaration_scope[-1][1] in FOREIGN)
        if declaration_foreign and not (tag in VOID or foreign):
            self.declaration_end(tag)
        # Only foreign elements and HTML void elements honor this flag.
        # A br start already supplied its separator and visibility attributes;
        # only a real end token is reprocessed as an attribute-free br start.
        if tag in VOID - {"br"} or foreign:
            self.handle_endtag(tag)
            if foreign and self.cdata_elem == tag:
                self.clear_cdata_mode()

    def handle_data(self, data):
        if self.cdata_elem == "script":
            position = 0
            while match := SCRIPT_TRANSITIONS.search(data, position):
                token = match.group().lower()
                if token == "<!--" and self.script_state == "data":
                    self.script_state = "escaped"
                elif token == "-->":
                    self.script_state = "data"
                elif token == "<script" and self.script_state == "escaped":
                    self.script_state = "double"
                # <!--> and <!---> include an overlapping --> transition.
                position = match.end() - 2 if token == "<!--" else match.end()
        if not self.skip and not self.content_scope and self.formatting_ambiguous():
            self.mark_formatting_ambiguous()
        if not self.skip and not self.content_scope and not (self.visibility and (self.visibility[-1]["hidden"] or self.visibility[-1]["closed_details"])):
            self.text.append(data)
            self.node.children.append(data)
            if self.heading is not None:
                self.heading.append(data)
            if self.caption is not None:
                self.caption.append(data)
            if self.cell is not None:
                self.cell.append(data)


class OfficialSources:
    def __init__(self, clock=None, fetch=None, previous=None, reviewed=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.fetch = fetch or self._fetch
        self.previous = previous or {}
        self.confirmed_entries = {}
        self._reviewed_input = reviewed
        self.reviewed_entries()

    def reviewed_entries(self):
        """Recheck edition authority on reuse, including retained proposals."""
        try:
            self.reviewed = validate_reviewed_guidance(load_reviewed_guidance() if self._reviewed_input is None else self._reviewed_input)
            self.reviewed_error = None
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
            # A malformed list supplies no guidance rather than partial trust.
            self.reviewed, self.reviewed_error = [], str(error)
        return self.reviewed

    @staticmethod
    def _fetch(url):
        request = Request(url, headers={"User-Agent": "Playbook-read-only-evidence/1", "Accept": "text/html"})
        with build_opener(OfficialRedirect()).open(request, timeout=20) as response:
            if urlparse(response.url).hostname != urlparse(url).hostname:
                raise ValueError("Nonofficial redirect")
            content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Source exceeds bounded retrieval")
            return content.decode("utf-8")

    def retrieve(self, urls=None, retained_guidance=()):
        reviewed = self.reviewed_entries()
        retained_guidance = [record for record in retained_guidance if matches_reviewed_guidance(record, reviewed)
                             and (record['source_url'] not in self.confirmed_entries
                                  or record['entry_fingerprint'] in self.confirmed_entries[record['source_url']])]
        evidence = {"guidance": [], "rates": [], "sources": [], "reviewed_models": [entry['model_id'] for entry in reviewed]}
        for url in SOURCES if urls is None else urls:
            try:
                page = Page()
                content = self.fetch(url)
                page.feed(content)
                page.close()
                checked = self.clock()
                source = {"source_url": url, "checked_at": self.previous.get(url, {}).get("checked_at"), "retrieved_at": checked, "status": "incomplete",
                          "uncertainty": "Retrieved official page; only unambiguous model-specific records are usable. Other data remains unknown."}
                if url == SOURCES[1]:
                    source["uncertainty"] = "Reasoning/control guidance retrieved separately. Task suitability is unknown from this source; supported reasoning still requires host evidence."
                # A nonempty page with only inert content still withdraws its
                # reviewed entries; it cannot preserve a prior confirmation.
                if not content.strip() or (not any(part.strip() for part in page.text)
                                          and not any(entry['source_url'] == url for entry in reviewed)):
                    raise ValueError("Empty source")
                source['content_fingerprint'] = hashlib.sha256(content.encode()).hexdigest()
                if url.endswith("pricing"):
                    records = self._rates(page, url, checked, [*retained_guidance, *evidence["guidance"]])
                    evidence["rates"].extend(records)
                    success = bool(records)
                else:
                    records, withdrawn = self._guidance(page, url, checked)
                    evidence["guidance"].extend(records)
                    if records or withdrawn:
                        self.confirmed_entries[url] = {record['entry_fingerprint'] for record in records}
                        retained_guidance = [record for record in retained_guidance if record['source_url'] != url]
                    if url in GUIDANCE_SOURCES.values():
                        source["uncertainty"] = ("Retrieved official page. Task fit comes only from the edition's reviewed guidance list "
                                                 "confirmed on this page; no task fit is inferred from page text.")
                        if self.reviewed_error:
                            source["uncertainty"] += " The reviewed guidance list is invalid, so no guidance is available: " + self.reviewed_error
                        if withdrawn:
                            source["uncertainty"] += " Withdrawn, " + WITHDRAWN + ": " + ", ".join(withdrawn) + "."
                    # Confirming or withdrawing a reviewed entry is itself a successful check.
                    success = bool(records or withdrawn)
                if success or url == SOURCES[1]:
                    source["status"] = "retrieved"
                    source["checked_at"] = checked
            except (OSError, ValueError, UnicodeError, TimeoutError):
                prior = self.previous.get(url, {})
                source = {"source_url": url, "checked_at": prior.get("checked_at"),
                          "status": "stale" if prior.get("checked_at") else "incomplete",
                          "uncertainty": "Retrieval failed. No fresh comparison; last successful date retained if known."}
            evidence["sources"].append(source)
        confirmed = {record['model_id'] for record in [*retained_guidance, *evidence['guidance']]}
        evidence['rates'] = [record for record in evidence['rates']
                             if record['provider'] != 'anthropic' or record['model_id'] in confirmed]
        return evidence

    def _guidance(self, page, url, checked):
        """Confirm reviewed entries for this source; never infer task fit from page text."""
        entries = [entry for entry in self.reviewed if entry["source_url"] == url]
        units = page_units(page.root) if entries else []
        records, withdrawn = [], []
        for entry in entries:
            if not confirms(entry, units):
                withdrawn.append(entry["model_id"])
                continue
            records.append({"model_id": entry["model_id"], "label": entry["label"], "provider": entry["provider"],
                            "tasks": list(entry["tasks"]), "risks": list(entry["risks"]), "text": rendered_text([entry["paragraph"]]),
                            "source_url": url, "checked_at": checked, "reviewed_at": entry["reviewed_at"],
                            "entry_fingerprint": entry_fingerprint(entry),
                            "uncertainty": f"Maintainer-reviewed provider statement (reviewed {entry['reviewed_at']}) confirmed unchanged on the "
                                           "official page; not measured project performance. Reasoning support comes from host discovery."})
        return records, withdrawn

    @staticmethod
    def _rates(page, url, checked, guidance=()):
        records = []
        if url == SOURCES[4]:
            names = {record["label"]: record["model_id"] for record in guidance
                     if record.get("provider") == "anthropic" and record.get("label") and valid_claim(record, "guidance", now=checked)}
            for table in page.tables:
                if (table["tier"] not in {"model pricing", "standard", "base api pricing"}
                        or not base_pricing_context(table["tier_context"])
                        or not base_pricing_context(table["caption"])
                        or "All prices are in USD" not in table["prefix"]
                        or not any(row == ["Name", "Input", "Output", "5m writes", "1h writes", "Hits and refreshes"] for row in table["rows"])):
                    continue
                for row in table["rows"]:
                    name = next((label for label in names if row and row[0] in {label, label + " For coding"}), None)
                    if not name or len(row) != 6:
                        continue
                    if not all(value == "-" or re.fullmatch(r"\$[0-9]+(?:\.[0-9]+)?\s*/\s*MTok", value)
                               for value in row[3:]):
                        continue
                    prices = [re.fullmatch(r"\$([0-9]+(?:\.[0-9]+)?)\s*/\s*MTok", value) for value in row[1:3]]
                    if not all(prices):
                        continue
                    amounts = [float(price[1]) for price in prices]
                    if not all(valid_rate_number(amount) for amount in amounts):
                        continue
                    records.append({"model_id": names[name], "provider": "anthropic", "currency": "USD", "unit": "1M tokens",
                                    "input": amounts[0], "output": amounts[1],
                                    "billing_route": "standard-base-uncached", "source_url": url, "checked_at": checked,
                                    "uncertainty": "Published API base rates, not subscription billing; excludes caching, tools, regional charges, taxes and negotiated billing."})
                break
            return records
        for table in page.tables:
            prefix = table["prefix"]
            rows = table["rows"]
            context = re.sub(r"[\s\-\u2010-\u2015]+", " ", table["tier_context"] + " " + table["caption"]).strip().lower()
            caption = re.sub(r"[\s\-\u2010-\u2015]+", " ", table["caption"]).strip().lower()
            short_label = r"short context(?: only| rates| pricing)?"
            if (url != SOURCES[2] or not re.search(r"per 1M tokens", prefix) or table["tier"] != "standard"
                    or re.search(r"\b(?:batch|priority|flex|fast|ultrafast|long context|extended context|above|over|exceeding)\b|>", context)
                    or caption and not re.fullmatch(short_label, caption)
                    or not rows):
                continue
            headers = next((row for row in rows if row and row[0] == "Model"), [])
            if headers not in (["Model", "Input", "Cached input", "Output"],
                               ["Model", "Input", "Cached input", "Cache writes", "Output", "Input", "Cached input", "Cache writes", "Output"]):
                continue
            output_index = 3 if len(headers) == 4 else 4
            if len(headers) == 4 and not (re.fullmatch(short_label, caption) or any(
                    re.fullmatch(short_label, re.sub(r"[\s\-\u2010-\u2015]+", " ", line).strip().lower())
                    for line in table["tier_context"].splitlines())):
                continue
            if len(headers) == 9 and ["", "Short context", "Long context"] not in rows:
                continue
            for row in rows:
                if len(row) != len(headers) or not re.fullmatch(r"[a-z0-9.-]+", row[0]):
                    continue
                prices = [row[1], row[output_index]]
                if not all(re.fullmatch(r"\$[0-9]+(?:\.[0-9]+)?", value) for value in prices):
                    continue
                amounts = [float(price[1:]) for price in prices]
                if not all(valid_rate_number(amount) for amount in amounts):
                    continue
                records.append({"model_id": row[0], "provider": "openai", "currency": "USD", "unit": "1M tokens",
                                "input": amounts[0], "output": amounts[1],
                                "billing_route": "standard-short-context-uncached", "source_url": url, "checked_at": checked,
                                "uncertainty": "Published API base rates only; excludes cache writes, tools, long context, regional uplifts, taxes and negotiated billing."})
            break
        return records


def successful_date_status(checked_at, now):
    """Classify the original successful date against the evaluation clock."""
    try:
        checked = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        current = datetime.fromisoformat(now.replace("Z", "+00:00")) if isinstance(now, str) else now
        if checked.tzinfo is None or current.tzinfo is None:
            return "incomplete"
        age = (current - checked).total_seconds()
        if age < 0:
            return "incomplete"
        return "retrieved" if age <= 86400 else "stale"
    except (ValueError, TypeError, AttributeError):
        return "incomplete"


def valid_claim(record, kind, now=None, allow_unusable=False):
    if not isinstance(record, dict) or not isinstance(record.get("uncertainty"), str) or not record["uncertainty"]:
        return False
    url = record.get("source_url")
    allowed = {SOURCES[0], SOURCES[3]} if kind == "guidance" else {SOURCES[2], SOURCES[4]}
    if not isinstance(url, str) or url not in allowed:
        return False
    # Cache assembly retains inadequate records for dated, honest display only.
    if allow_unusable:
        return True
    status = record.get("status")
    # An absent status is the official adapter's successful-claim format.
    # Every explicit status must affirm success; untrusted containers must
    # never reach hash-based membership or become evidence authority.
    if status is not None and (not isinstance(status, str) or status != "retrieved"):
        return False
    return successful_date_status(record.get("checked_at"),
                                  now if now is not None else datetime.now(timezone.utc)) == "retrieved"


def supported_estimate(estimate, rate, requested_workload):
    """Validate a supplied subtotal against its selected rate, without replacing it."""
    if not isinstance(estimate, dict) or not isinstance(rate, dict):
        return False
    workload = estimate.get("assumptions")
    if (not isinstance(workload, dict) or not isinstance(requested_workload, dict)
            or workload != requested_workload
            or estimate.get("status") not in (None, "retrieved")
            or workload.get("billing_route") != rate.get("billing_route")
            or any(type(counts.get(key)) is not int or not 0 <= counts[key] <= 2 ** 53 - 1
                   for counts in (workload, requested_workload)
                   for key in ("input_tokens", "output_tokens", "retries"))
            or any(estimate.get(key) != rate.get(key)
                   for key in ("currency", "source_url", "checked_at"))
            or any(not isinstance(estimate.get(key), str) or not estimate[key]
                   for key in ("label", "uncertainty"))):
        return False
    expected = (workload["input_tokens"] * rate["input"]
                + workload["output_tokens"] * rate["output"]) / 1_000_000 * (1 + workload["retries"])
    amount = estimate.get("amount")
    # Bounded inputs make expected finite. Equality also rejects nonfinite and
    # arbitrarily large caller amounts without converting huge integers to float.
    return type(amount) in (int, float) and math.isfinite(expected) and amount == expected


def guidance_supports(claim, choice, context):
    """The selected claim must support this identity and the requested task fit."""
    if not isinstance(choice, dict) or not isinstance(context, dict):
        return False
    goal = context.get("goal", "")
    if not isinstance(goal, str):
        return False
    task = context.get("task")
    if "task" not in context:
        if re.search(r"implement|cod(e|ing)|software|test|repair|parser|\bapi\b|application|build|refactor", goal, re.I):
            task = "coding"
        elif re.search(r"analy[sz]|research|reason|plan|document", goal, re.I):
            task = "analysis"
    risk = context.get("risk", "high" if re.search(
        r"security|billing|financial|medical|privacy|authentication|permission", goal, re.I) else "ordinary")
    return (all(isinstance(choice.get(key), str) and choice[key] and claim.get(key) == choice[key]
                for key in ("model_id", "provider"))
            and isinstance(claim.get("text"), str) and bool(claim["text"])
            and all(isinstance(value, str) and bool(value.strip())
                    and isinstance(claim.get(key), list)
                    and all(isinstance(element, str) and bool(element.strip())
                            for element in claim[key])
                    and value in claim[key]
                    for key, value in (("tasks", task), ("risks", risk)))
            and isinstance(choice.get("reasoning"), str) and bool(choice["reasoning"])
            and ("reasoning" not in claim or isinstance(claim["reasoning"], list)
                 and choice["reasoning"] in claim["reasoning"]))


def project_advice(advice, now, requested_workload=None, requested_context=None, reviewed=None):
    """Recheck only original selected claims; never retrieve or rank a substitute."""
    result = deepcopy(advice) if isinstance(advice, dict) else {}
    result.setdefault("choice", None)
    result.setdefault("guidance", None)
    result.setdefault("cost", None)
    result.setdefault("limitations", LIMITATIONS)
    retained = result.get("withheld_evidence", {})
    withheld = deepcopy(retained) if isinstance(retained, dict) else {"guidance": retained}
    guidance = result.get("guidance")
    billing = result.get("cost")
    if billing is not None and not isinstance(billing, dict):
        withheld["rates"] = billing
        result["cost"] = {"rates": None, "estimate": None}
    pricing = (result.get("cost") or {}).get("rates")
    if guidance is None and result.get("choice") is not None:
        withheld["guidance"] = {"checked_at": None, "status": "incomplete"}
    if result.get("cost") and pricing is None:
        result["cost"]["estimate"] = None
    for kind, claim in (("guidance", guidance), ("rates", pricing)):
        try:
            usable = (isinstance(claim, dict) and claim.get("status") in (None, "retrieved")
                      and valid_claim(claim, kind, now=now))
            if usable and kind == "guidance":
                usable = (guidance_supports(claim, result.get("choice"), requested_context)
                          and (reviewed is None or matches_reviewed_guidance(claim, reviewed)))
            if usable and kind == "rates":
                choice = result.get("choice")
                usable = (isinstance(choice, dict) and billing.get("billing") == "api"
                          and billing.get("route") == choice
                          and all(isinstance(choice.get(key), str) and choice[key]
                                  and claim.get(key) == choice[key] for key in ("model_id", "provider"))
                          and claim.get("currency") == "USD" and claim.get("unit") == "1M tokens"
                          and isinstance(claim.get("billing_route"), str) and bool(claim["billing_route"])
                          and all(valid_rate_number(claim.get(key)) for key in ("input", "output")))
        except (TypeError, ValueError, AttributeError):
            usable = False
        if claim is not None and not usable:
            withheld[kind] = deepcopy(claim)
    if not isinstance(advice, dict):
        withheld["guidance"] = advice
    if "guidance" in withheld:
        # Withholding suitability also hides cost. Retain its independently
        # dated selected claim before dropping the public cost projection.
        if pricing is not None:
            withheld.setdefault("rates", deepcopy(pricing))
        result.update(choice=None, guidance=None, cost=None, local_outcomes=None,
                      rationale="Original task-fit evidence is inadequate; suitability unknown. Retain the saved or edited choice.")
    elif "rates" in withheld and result.get("cost"):
        result["cost"].update(rates=None, estimate=None)
        result["cost"]["limitations"] = "Original pricing evidence is inadequate; rates and token subtotal unknown."
    elif result.get("cost"):
        estimate = result["cost"].get("estimate")
        if estimate is not None and not supported_estimate(estimate, pricing, requested_workload):
            withheld["estimate"] = deepcopy(estimate)
            result["cost"]["estimate"] = None
            result["cost"]["limitations"] = "Original subtotal is unsupported by the selected rate and workload assumptions; token subtotal unknown."
    if withheld:
        for kind, claim in list(withheld.items()):
            if not isinstance(claim, dict):
                claim = {"original": claim, "checked_at": None}
                withheld[kind] = claim
            status = successful_date_status(claim.get("checked_at"), now)
            if status != "retrieved":
                claim["status"] = status
            elif claim.get("status") not in ("stale", "incomplete", "failed"):
                claim["status"] = "incomplete"
        result["withheld_evidence"] = withheld
        result["limitations"] = (LIMITATIONS + " Original successful dates retained in withheld evidence; "
                                 "stale or incomplete claims cannot support advice or costs. "
                                 "Use explicit Refresh or the ordinary role editor to recover.")
    return result


def local_outcome(choice, context):
    workload = context.get("workload")
    if not isinstance(workload, dict) or not workload:
        return None
    for record in context.get("outcomes", []):
        if not isinstance(record, dict):
            continue
        source = record.get("source_url", "")
        if (not isinstance(source, str) or not re.fullmatch(r"project-evidence://[A-Za-z0-9_-]+", source)
                or record.get("verified") is not True or record.get("task") != context.get("task")
                or record.get("risk") != context.get("risk", "ordinary") or record.get("workload") != workload
                or any(record.get(key) != choice.get(key) for key in ("model_id", "runner", "reasoning", "provider"))
                or not record.get("uncertainty") or not isinstance(record.get("summary"), str)):
            continue
        try:
            if datetime.fromisoformat(record["checked_at"].replace("Z", "+00:00")).tzinfo is None:
                continue
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        return {key: deepcopy(record[key]) for key in ("source_url", "checked_at", "uncertainty", "summary", "workload")}
    return None


def cost(choice, context, evidence, now=None):
    now = now if now is not None else datetime.now(timezone.utc)
    route_key = "@".join(choice[key] for key in ("model_id", "runner", "reasoning"))
    billing = context.get("route_billing", {}).get(route_key, context.get("route_billing", {}).get(choice["runner"], context.get("billing", "unknown")))
    result = {"billing": billing, "route": deepcopy(choice), "rates": None, "estimate": None, "observable": None,
              "limitations": "Usage, allowance and verified total outcome cost are unknown. API rates are not subscription bills."}
    if billing != "api":
        observation = context.get("observations", {}).get(route_key, context.get("observations", {}).get(choice["runner"]))
        if isinstance(observation, dict) and all(observation.get(key) for key in ("source_url", "checked_at", "uncertainty", "usage_or_limit")):
            try:
                checked = datetime.fromisoformat(observation["checked_at"].replace("Z", "+00:00"))
                if checked.tzinfo is not None and isinstance(observation["source_url"], str) and urlparse(observation["source_url"]).scheme:
                    result["observable"] = {key: observation[key] for key in ("source_url", "checked_at", "uncertainty", "usage_or_limit")}
                    result["limitations"] = "Only the attached usage/limit is observed. Unobserved consumption, allowance periods and verified outcome costs remain unknown; API rates are not subscription bills."
            except (ValueError, TypeError, AttributeError):
                pass
        return result
    rates = [record for record in evidence.get("rates", []) if valid_claim(record, "rates", now=now)
             and record.get("model_id") == choice["model_id"] and record.get("provider") == choice.get("provider")
             and record.get("currency") == "USD" and record.get("unit") == "1M tokens"
             and isinstance(record.get("billing_route"), str)
             and all(valid_rate_number(record.get(key)) for key in ("input", "output"))]
    workload = context.get("workload", {})
    selected = [record for record in rates if record["billing_route"] == workload.get("billing_route")]
    if len(selected) == 1:
        result["rates"] = deepcopy(selected[0])
    elif len(rates) == 1:
        result["rates"] = deepcopy(rates[0])
    rate = result["rates"]
    if (rate and workload.get("billing_route") == rate["billing_route"]
            and all(type(workload.get(key)) is int and workload[key] >= 0 for key in ("input_tokens", "output_tokens", "retries"))):
        if any(workload[key] > 2 ** 53 - 1 for key in ("input_tokens", "output_tokens", "retries")):
            result["limitations"] += " Workload exceeds numeric bounds (each count must be at most 2^53 - 1); token subtotal unknown."
            return result
        amount = (workload["input_tokens"] * rate["input"] + workload["output_tokens"] * rate["output"]) / 1_000_000 * (1 + workload["retries"])
        if math.isfinite(amount):
            result["estimate"] = {"amount": amount, "currency": rate["currency"], "label": "Assumed API token subtotal, not a bill or verified outcome",
                                  "assumptions": deepcopy(workload), "source_url": rate["source_url"], "checked_at": rate["checked_at"],
                                  "uncertainty": "Every retry assumes the same tokens; excludes all charges outside the published base rate."}
    return result


def recommendations(routes, context, evidence, allowed_runners, lane=False, now=None):
    now = now if now is not None else datetime.now(timezone.utc)
    inferred = context is None or "task" not in context or "risk" not in context
    context = deepcopy(context or {})
    for key in ("constraints", "workload", "route_billing", "observations"):
        if key in context and not isinstance(context[key], dict):
            raise ValueError("Advice context requires structured, local evidence; no defaults changed.")
    if not isinstance(context.get("outcomes", []), list):
        raise ValueError("Project outcomes must be a local list of comparable observations.")
    if any(not isinstance(value, dict) for value in context.get("constraints", {}).values()):
        raise ValueError("Each role constraint must be an owning-gate record.")
    for constraint in context.get("constraints", {}).values():
        if any(key in constraint and type(constraint[key]) is not bool for key in ("authority", "permission", "independent")):
            raise ValueError("Gate checks must be explicit booleans.")
        for key in ("allowed_models", "allowed_reasoning", "excluded_models"):
            if key in constraint and (not isinstance(constraint[key], list) or any(not isinstance(value, str) for value in constraint[key])):
                raise ValueError("Gate exclusions and allowed identities must be lists.")
    goal = context.get("goal", "")
    if "task" not in context:
        if re.search(r"implement|cod(e|ing)|software|test|repair|parser|\bapi\b|application|build|refactor", goal, re.I):
            context["task"] = "coding"
        elif re.search(r"analy[sz]|research|reason|plan|document", goal, re.I):
            context["task"] = "analysis"
    if "risk" not in context:
        context["risk"] = "high" if re.search(r"security|billing|financial|medical|privacy|authentication|permission", goal, re.I) else "ordinary"
    task, risk = context.get("task"), context.get("risk", "ordinary")
    result = {}
    for role, alternatives in routes.items():
        constraints = context.get("constraints", {}).get(role, {})
        required = ["authority", "permission"] + (["independent"] if role == "verification" else [])
        permitted = all(constraints.get(key) is True for key in required) if lane else not any(constraints.get(key) is False for key in required)
        eligible = []
        for choice in alternatives:
            if not permitted or choice["runner"] not in allowed_runners:
                continue
            if (constraints.get("excluded_models") and choice["model_id"] in constraints["excluded_models"]
                    or constraints.get("allowed_models") is not None and choice["model_id"] not in constraints["allowed_models"]
                    or constraints.get("allowed_reasoning") is not None and choice["reasoning"] not in constraints["allowed_reasoning"]):
                continue
            for record in evidence.get("guidance", []):
                if (valid_claim(record, "guidance", now=now) and guidance_supports(record, choice, context)):
                    eligible.append((choice, record))
                    break
        advice = {"role": role, "choice": None, "guidance": None, "cost": None, "local_outcomes": None,
                  "rationale": "No verified suitable route for this task/risk and gate constraints; retain effective preference and choose explicitly.",
                  "limitations": LIMITATIONS, "sources": deepcopy(evidence.get("sources", []))}
        confirmed = {record.get("model_id") for record in evidence.get("guidance", [])}
        reviewed = set(evidence.get('reviewed_models', confirmed))
        unreviewed = sorted({choice["model_id"] for choice in alternatives if choice["model_id"] not in reviewed})
        withdrawn = sorted({choice['model_id'] for choice in alternatives if choice['model_id'] in reviewed - confirmed})
        notices = []
        if unreviewed:
            notices.append("No reviewed guidance yet for " + ", ".join(unreviewed) + ".")
        if withdrawn:
            notices.append("Reviewed guidance withdrawn for " + ", ".join(withdrawn) + ": " + WITHDRAWN + ".")
        if eligible:
            choice, guidance = eligible[0]
            advice.update(choice=deepcopy(choice), guidance=deepcopy(guidance), cost=cost(choice, context, evidence, now=now), local_outcomes=local_outcome(choice, context),
                          rationale=f"For {context.get('goal', 'the current task')}: {task}, {risk} risk; provider guidance supports task fit. {role} uses host-supported {choice['reasoning']} reasoning on {choice['runner']}. First eligible route in discovery order, not a price or performance ranking. Local comparative outcomes unknown.")
            if advice["local_outcomes"]:
                advice["rationale"] = advice["rationale"].replace("Local comparative outcomes unknown.", "Comparable local observation attached separately; no cross-model cheapest-outcome claim.")
            if inferred:
                advice["limitations"] += " Task/risk inferred from goal, not measured; supply explicit task and risk to correct advice."
        for notice in notices:
            advice['rationale'] += ' ' + notice
            advice['limitations'] += ' ' + notice
        result[role] = advice
    return result
