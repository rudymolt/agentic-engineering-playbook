#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
HTML_FILES = sorted(
    path
    for path in ROOT.rglob("*.html")
    if "backups" not in path.parts
    and "backup" not in path.name
)


class DocParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.terms: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.buttons: list[dict[str, str]] = []
        self.explainers: list[str] = []
        self.explainer_json = ""
        self._capture_explainer_json = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if "id" in data:
            self.ids.append(data["id"])
        if tag == "a" and data.get("href"):
            self.links.append((data.get("href", ""), data.get("id", "")))
        if "data-def" in data:
            self.terms.append(data["data-def"])
        if tag in {"h1", "h2", "h3"}:
            self.headings.append((int(tag[1]), data.get("id", "")))
        if tag == "button":
            self.buttons.append(data)
        if "data-explainer" in data:
            self.explainers.append(data["data-explainer"])
        if tag == "script" and data.get("id") == "playbook-explainers":
            self._capture_explainer_json = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._capture_explainer_json = False

    def handle_data(self, data: str) -> None:
        if self._capture_explainer_json:
            self.explainer_json += data


def glossary_keys() -> set[str]:
    source = (ROOT / "assets" / "playbook-glossary.js").read_text()
    block = source.split("window.PLAYBOOK_GLOSSARY = {", 1)[1].rsplit("};", 1)[0]
    return set(re.findall(r"\n\s*([a-zA-Z][\w-]*):\s*\{", block))


def local_target_exists(path: Path, href: str) -> bool:
    parsed = urlsplit(href)
    if parsed.scheme or href.startswith("#"):
        return True
    if not parsed.path:
        return True
    target = (path.parent / unquote(parsed.path)).resolve()
    try:
        target.relative_to(ROOT.parent)
    except ValueError:
        return False
    if target.is_dir():
        target = target / "index.html"
    return target.exists()


def touch_target_covered(button: dict[str, str]) -> bool:
    classes = set(button.get("class", "").split())
    if "term" in classes:
        return True
    if "pop-close" in classes:
        return True
    if classes & {"copy-button", "small-action"}:
        return True
    if any(key.startswith("data-") for key in button):
        return True
    return False


def check_file(path: Path, glossary: set[str]) -> list[str]:
    parser = DocParser()
    parser.feed(path.read_text())
    problems: list[str] = []

    seen: set[str] = set()
    for element_id in parser.ids:
        if element_id in seen:
            problems.append(f"{path}: duplicate id '{element_id}'")
        seen.add(element_id)

    for href, _ in parser.links:
        if not local_target_exists(path, href):
            problems.append(f"{path}: broken local link '{href}'")

    for term in sorted(set(parser.terms) - glossary):
        problems.append(f"{path}: glossary term '{term}' has no shared definition")

    previous = 0
    for level, _ in parser.headings:
        if previous and level > previous + 1:
            problems.append(f"{path}: heading jumps from h{previous} to h{level}")
        previous = level

    # V0.2.1: templates/ HTML files are starter specimens copied into projects,
    # not live playbook docs — their buttons are visual exhibits, so the
    # touch-target rule does not apply there. (It previously produced 83
    # permanent warnings, which trained everyone to ignore the checker.)
    if "templates" not in path.parts:
        for index, button in enumerate(parser.buttons, start=1):
            if not touch_target_covered(button):
                problems.append(f"{path}: button #{index} lacks touch-target coverage marker")

    if parser.explainers:
        defined: set[str] = set()
        if parser.explainer_json.strip():
            try:
                defined = set(json.loads(parser.explainer_json).keys())
            except json.JSONDecodeError as exc:
                problems.append(f"{path}: invalid explainer JSON: {exc}")
        for key in sorted(set(parser.explainers) - defined):
            problems.append(f"{path}: explainer trigger '{key}' has no JSON entry")

    return problems


def main() -> int:
    glossary = glossary_keys()
    problems: list[str] = []
    for path in HTML_FILES:
        problems.extend(check_file(path, glossary))

    if problems:
        print("Interactive doc checks failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print(f"Interactive doc checks passed for {len(HTML_FILES)} HTML files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
