#!/usr/bin/env python3
"""Report whether official pages still confirm each reviewed guidance entry.

Run before a release. Without --page the official sources are fetched; supply
--page URL=FILE to check retained bytes offline. Exit 0 when every entry is
confirmed, 1 when any is withdrawn or unretrievable, 2 for an invalid list.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_recommendations import (REVIEWED_GUIDANCE, WITHDRAWN, OfficialSources, Page, confirms,
                                   load_reviewed_guidance, page_units)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guidance", type=Path, default=REVIEWED_GUIDANCE)
    parser.add_argument("--page", action="append", default=[], metavar="URL=FILE")
    args = parser.parse_args(argv)
    try:
        entries = load_reviewed_guidance(args.guidance)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"invalid reviewed guidance list: {error}")
        return 2
    supplied = {}
    for item in args.page:
        url, separator, path = item.partition("=")
        if not separator:
            parser.error("--page requires URL=FILE")
        supplied[url] = Path(path).read_text(encoding="utf-8")
    failed = False
    units = {}
    for entry in entries:
        url = entry["source_url"]
        if url not in units:
            try:
                page = Page()
                page.feed(supplied[url] if url in supplied else OfficialSources._fetch(url))
                page.close()
                units[url] = page_units(page.root)
            except (OSError, ValueError, UnicodeError, TimeoutError) as error:
                units[url] = error
        if isinstance(units[url], Exception):
            print(f"unretrieved {entry['model_id']} {url}: {units[url]}")
            failed = True
        elif confirms(entry, units[url]):
            print(f"confirmed {entry['model_id']} {url} (reviewed {entry['reviewed_at']})")
        else:
            print(f"{WITHDRAWN}: {entry['model_id']} {url} (reviewed {entry['reviewed_at']})")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
