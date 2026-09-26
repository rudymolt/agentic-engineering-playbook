#!/usr/bin/env python3
"""Glossary progressive-disclosure tooling (added V0.2.10).

Borrows OKF's progressive-disclosure and bundle-relative-link ideas for the
project design glossary (and ADRs) WITHOUT the OKF `type` frontmatter or any
type-conformance lint. See references/okf/okf-explainer.md and
analysis/okf-progressive-glossary-plan.md.

A *split* glossary is a directory:

    design-glossary/
    ├── index.md                 # progressive-disclosure index (read first)
    └── components/<term>.md      # one entry per file

Subcommands
-----------
  split <SOURCE.md> <OUTDIR>     Split a monolith DESIGN-GLOSSARY.md into the
                                 directory form and generate index.md.
  build-index <GLOSSARY_DIR>     Regenerate index.md from components/*.md.
  check <GLOSSARY_DIR>           Lint: index/entries in sync, sibling
                                 cross-links resolve, every entry anchors to the
                                 kitchen sink. Exit 0 = clean (mirrors
                                 check-md-conventions.py).
  adr-index <ADR_DIR>            Regenerate docs/adr/index.md from NNNN-*.md.
  check-adr <ADR_DIR>            Lint: ADR index in sync, ADR cross-links resolve.

Stdlib only. Run from the project root, e.g.:
  python3 {playbook-path}/v0.5/scripts/check-glossary.py check ./design-glossary
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# --- entry parsing -----------------------------------------------------------

# A real glossary entry (as opposed to a category bucket like "### Containers")
# is an `### {term}` block whose body contains a one-line definition marker.
ENTRY_MARKER = "**One-line definition.**"
ANCHOR_RE = re.compile(r"\*\*Kitchen-sink anchor\.\*\*\s*(\[[^\]]*\]\([^)]*\))")
ANCHOR_LINK_RE = re.compile(r"^\[([^\]]+)\]\(([^)#]*)(#([\w-]+))\)$")
ONELINE_RE = re.compile(r"\*\*One-line definition\.\*\*\s*(.+)")
H3_RE = re.compile(r"^### +(.+?)\s*$", re.M)
BACKTICK_TOKEN_RE = re.compile(r"`([a-z0-9][a-z0-9-]+)`")


def slugify(term: str) -> str:
    term = term.strip().strip("`").strip()
    term = term.lower().replace(" ", "-")
    return re.sub(r"[^a-z0-9-]", "", term)


def parse_entries(text: str) -> list[dict]:
    """Return real entries from a monolith glossary: [{term, slug, body}]."""
    # Blank out fenced code blocks (keeping line count) so the `### {term}`
    # example inside the "Entry template" fence is not mistaken for an entry.
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"),
                  text, flags=re.S)
    heads = list(H3_RE.finditer(text))
    entries: list[dict] = []
    for i, m in enumerate(heads):
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        # stop at the next H2 if one falls inside this block
        h2 = re.search(r"^## +", text[start:end], re.M)
        if h2:
            end = start + h2.start()
        body = text[start:end].strip()
        if ENTRY_MARKER not in body:
            continue  # category bucket / placeholder, not a real entry
        term = m.group(1).strip()
        entries.append({"term": term, "slug": slugify(term), "body": body})
    return entries


def oneline_of(body: str) -> str:
    m = ONELINE_RE.search(body)
    return m.group(1).strip() if m else ""


def anchor_of(body: str) -> str:
    m = ANCHOR_RE.search(body)
    return m.group(1).strip() if m else ""


def anchor_parts(anchor: str) -> tuple[str, str, str] | None:
    """Return (label, href_path, fragment_id) for a kitchen-sink markdown link."""
    m = ANCHOR_LINK_RE.match(anchor)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(4)


def rel_link_path(target: Path, from_dir: Path) -> str:
    rel = os.path.relpath(target, start=from_dir)
    rel = rel.replace(os.sep, "/")
    if not rel.startswith("."):
        rel = f"./{rel}"
    return rel


def rebase_anchor_link(anchor: str, source_file: Path, dest_file: Path) -> str:
    """Rewrite an anchor link so the same target works from a different file."""
    parts = anchor_parts(anchor)
    if parts is None:
        return anchor
    label, href_path, fragment = parts
    if not href_path or re.match(r"^[a-z][a-z0-9+.-]*:", href_path):
        return anchor
    target = (source_file.parent / href_path).resolve()
    rebased = rel_link_path(target, dest_file.parent.resolve())
    return f"[{label}]({rebased}#{fragment})"


def rebase_entry_anchor(body: str, source_file: Path, dest_file: Path) -> str:
    anchor = anchor_of(body)
    if not anchor:
        return body
    rebased = rebase_anchor_link(anchor, source_file, dest_file)
    return body.replace(anchor, rebased, 1)


def related_slugs(body: str, all_slugs: set[str], self_slug: str) -> list[str]:
    """Other component slugs referenced (backtick-quoted) in this entry's body."""
    found = {t for t in BACKTICK_TOKEN_RE.findall(body) if t in all_slugs}
    found.discard(self_slug)
    return sorted(found)


# --- index rendering ---------------------------------------------------------

INDEX_HEADER = (
    "# Design glossary — index\n\n"
    "> Progressive-disclosure index. **Read this first**; open only the "
    "component entries a feature actually touches. Regenerate with "
    "`check-glossary.py build-index`.\n\n"
    "## Components\n\n"
)


def render_index(entries: list[dict], index_path: Path | None = None) -> str:
    lines = [INDEX_HEADER]
    for e in sorted(entries, key=lambda x: x["slug"]):
        anchor = anchor_of(e["body"])
        if anchor and index_path is not None and "path" in e:
            anchor = rebase_anchor_link(anchor, e["path"], index_path)
        suffix = f" {anchor}" if anchor else ""
        lines.append(f"* [{e['slug']}](components/{e['slug']}.md) — {oneline_of(e['body'])}{suffix}\n")
    return "".join(lines)


def render_entry_file(e: dict, related: list[str]) -> str:
    out = f"# {e['term']}\n\n{e['body']}\n"
    if related:
        links = ", ".join(f"[{s}]({s}.md)" for s in related)
        out += f"\n**Related.** {links}\n"
    return out


# --- subcommands -------------------------------------------------------------

def cmd_split(args) -> int:
    source = Path(args.source)
    outdir = Path(args.outdir)
    text = source.read_text()
    entries = parse_entries(text)
    if not entries:
        print(f"No glossary entries (blocks with '{ENTRY_MARKER}') found in {source}")
        return 1
    all_slugs = {e["slug"] for e in entries}
    comp = outdir / "components"
    comp.mkdir(parents=True, exist_ok=True)
    written_entries = []
    for e in entries:
        rel = related_slugs(e["body"], all_slugs, e["slug"])
        entry_path = comp / f"{e['slug']}.md"
        entry = dict(e)
        entry["body"] = rebase_entry_anchor(e["body"], source, entry_path)
        entry["path"] = entry_path
        entry_path.write_text(render_entry_file(entry, rel))
        written_entries.append(entry)
    index = outdir / "index.md"
    index.write_text(render_index(written_entries, index))
    print(f"Split {len(entries)} entries into {comp}/ and wrote {outdir/'index.md'}")
    return 0


def load_entry_files(glossary_dir: Path) -> list[dict]:
    comp = glossary_dir / "components"
    entries = []
    for f in sorted(comp.glob("*.md")):
        body = f.read_text()
        entries.append({"term": f.stem, "slug": f.stem, "body": body, "path": f})
    return entries


def cmd_build_index(args) -> int:
    glossary_dir = Path(args.glossary_dir)
    entries = load_entry_files(glossary_dir)
    if not entries:
        print(f"No component files under {glossary_dir/'components'}")
        return 1
    index = glossary_dir / "index.md"
    index.write_text(render_index(entries, index))
    print(f"Rebuilt {glossary_dir/'index.md'} from {len(entries)} component files")
    return 0


def cmd_check(args) -> int:
    glossary_dir = Path(args.glossary_dir)
    problems: list[str] = []
    comp = glossary_dir / "components"
    index = glossary_dir / "index.md"
    if not comp.is_dir():
        print(f"{comp} not found — is this a split glossary?")
        return 1
    entries = load_entry_files(glossary_dir)
    slugs = {e["slug"] for e in entries}

    # 1 — index in sync with entries
    if not index.exists():
        problems.append("index.md missing")
    else:
        index_text = index.read_text()
        expected_index = render_index(entries, index)
        if index_text != expected_index:
            problems.append("index.md: generated content is stale; run build-index")
        indexed = set(re.findall(r"\]\(components/([\w-]+)\.md\)", index_text))
        for missing in sorted(slugs - indexed):
            problems.append(f"index.md: entry '{missing}' has no index line")
        for extra in sorted(indexed - slugs):
            problems.append(f"index.md: lists non-existent entry '{extra}'")

    # 2 — sibling cross-links resolve + 3 — each entry anchors the kitchen sink
    for e in entries:
        for target in re.findall(r"\]\(([\w-]+)\.md\)", e["body"]):
            if target not in slugs:
                problems.append(f"{e['slug']}.md: broken cross-link to '{target}.md'")
        if anchor_of(e["body"]) == "":
            problems.append(f"{e['slug']}.md: no '**Kitchen-sink anchor.**' line")

    # optional — kitchen-sink anchor ids actually exist
    if args.kitchen_sink:
        kitchen_sink = Path(args.kitchen_sink).resolve()
        ks = kitchen_sink.read_text()
        ids = set(re.findall(r'id=["\']([\w-]+)["\']', ks))
        for e in entries:
            anchor = anchor_of(e["body"])
            parts = anchor_parts(anchor)
            if parts is None:
                continue
            _, href_path, fragment = parts
            if href_path:
                target = (e["path"].parent / href_path).resolve()
                if target != kitchen_sink:
                    problems.append(
                        f"{e['slug']}.md: kitchen-sink link points to {href_path}, "
                        f"not {rel_link_path(kitchen_sink, e['path'].parent.resolve())}"
                    )
            if fragment not in ids:
                problems.append(f"{e['slug']}.md: kitchen-sink anchor #{fragment} not found")

    if problems:
        print("Glossary checks failed:")
        for p in problems:
            print(f"- {p}")
        return 1
    print(f"Glossary checks passed: {len(entries)} entries, index in sync, links resolve.")
    return 0


# --- ADR modes ---------------------------------------------------------------

ADR_FILE_RE = re.compile(r"^(\d{4})-[\w-]+\.md$")


def load_adrs(adr_dir: Path) -> list[dict]:
    out = []
    for f in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        text = f.read_text()
        title = ""
        status = ""
        date = ""
        mt = re.search(r"^#\s*ADR\s*\d+\s*[—-]\s*(.+)$", text, re.M)
        if mt:
            title = mt.group(1).strip()
        ms = re.search(r"^Status:\s*(.+)$", text, re.M)
        if ms:
            status = ms.group(1).strip()
        md = re.search(r"^Date:\s*(.+)$", text, re.M)
        if md:
            date = md.group(1).strip()
        out.append({"file": f.name, "num": f.name[:4], "title": title,
                    "status": status, "date": date, "text": text})
    return out


def cmd_adr_index(args) -> int:
    adr_dir = Path(args.adr_dir)
    adrs = load_adrs(adr_dir)
    if not adrs:
        print(f"No ADRs (NNNN-*.md) under {adr_dir}")
        return 1
    lines = ["# ADR index\n\n",
             "> Generated with `check-glossary.py adr-index`. One line per decision.\n\n"]
    for a in adrs:
        bits = " · ".join(b for b in (a["status"], a["date"]) if b)
        meta = f" — {bits}" if bits else ""
        lines.append(f"* [ADR {a['num']} — {a['title']}]({a['file']}){meta}\n")
    (adr_dir / "index.md").write_text("".join(lines))
    print(f"Wrote {adr_dir/'index.md'} from {len(adrs)} ADRs")
    return 0


def cmd_check_adr(args) -> int:
    adr_dir = Path(args.adr_dir)
    problems: list[str] = []
    adrs = load_adrs(adr_dir)
    files = {a["file"] for a in adrs}
    index = adr_dir / "index.md"
    if index.exists():
        indexed = set(re.findall(r"\]\(([\w-]+\.md)\)", index.read_text()))
        for missing in sorted(files - indexed):
            problems.append(f"index.md: ADR '{missing}' has no index line")
        for extra in sorted(indexed - files):
            problems.append(f"index.md: lists non-existent ADR '{extra}'")
    else:
        problems.append("index.md missing")
    for a in adrs:
        for target in re.findall(r"\]\((\d{4}-[\w-]+\.md)\)", a["text"]):
            if target not in files:
                problems.append(f"{a['file']}: broken ADR link to '{target}'")
    if problems:
        print("ADR checks failed:")
        for p in problems:
            print(f"- {p}")
        return 1
    print(f"ADR checks passed: {len(adrs)} ADRs, index in sync, links resolve.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Glossary/ADR progressive-disclosure tooling")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("split"); sp.add_argument("source"); sp.add_argument("outdir")
    sp.set_defaults(func=cmd_split)

    bi = sub.add_parser("build-index"); bi.add_argument("glossary_dir")
    bi.set_defaults(func=cmd_build_index)

    ck = sub.add_parser("check"); ck.add_argument("glossary_dir")
    ck.add_argument("--kitchen-sink", default=None)
    ck.set_defaults(func=cmd_check)

    ai = sub.add_parser("adr-index"); ai.add_argument("adr_dir")
    ai.set_defaults(func=cmd_adr_index)

    ca = sub.add_parser("check-adr"); ca.add_argument("adr_dir")
    ca.set_defaults(func=cmd_check_adr)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
