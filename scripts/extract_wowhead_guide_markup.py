#!/usr/bin/env python3
"""Extract Wowhead guide body markup and item/spell IDs from saved HTML.

Wowhead guide pages rely heavily on JavaScript: the visible listview divs are
empty in the raw HTML. The actual guide content (including all [item=id] and
[spell=id] references) is embedded in a script tag as the argument to
WH.markup.printHtml("..."). This script extracts that markup from already-
downloaded HTML so you can get full BiS item data without running a browser.

Usage:
  python3 extract_wowhead_guide_markup.py downloads/wowhead_tbc_bis/druid-balance
  python3 extract_wowhead_guide_markup.py --items-only path/to/guide.html
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import List, Set, Tuple

# Match WH.markup.printHtml(" ... "); the string can be huge and contain \", \\n, etc.
# We look for printHtml( then consume a double-quoted string with allowed escapes.
PRINT_HTML_RE = re.compile(
    r"WH\.markup\.printHtml\s*\(\s*\"((?:[^\"\\]|\\.)*)\"\s*\)",
    re.S,
)
# Fallback: sometimes the string is built from concatenation; grab first big quoted part.
PRINT_HTML_FALLBACK_RE = re.compile(
    r"WH\.markup\.printHtml\s*\(\s*\"((?:[^\"\\]|\\.){100,}?)\"",
    re.S,
)

ITEM_TAG_RE = re.compile(r"\[item=(\d+)\]")
SPELL_TAG_RE = re.compile(r"\[spell=(\d+)\]")
ENCHANT_TAG_RE = re.compile(r"\[enchant=(\d+)\]")


def extract_print_html_payload(html: str) -> str | None:
    """Extract the string argument to WH.markup.printHtml("...") from guide HTML."""
    m = PRINT_HTML_RE.search(html)
    if m:
        raw = m.group(1)
        # Unescape JS string: \\ -> \, \" -> ", \n -> newline, etc.
        return (
            raw.replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )
    m = PRINT_HTML_FALLBACK_RE.search(html)
    if m:
        raw = m.group(1)
        return (
            raw.replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )
    return None


def extract_ids_from_markup(markup: str) -> Tuple[List[int], List[int], List[int]]:
    """Return (item_ids, spell_ids, enchant_ids) from Wowhead markup."""
    item_ids = list(map(int, ITEM_TAG_RE.findall(markup)))
    spell_ids = list(map(int, SPELL_TAG_RE.findall(markup)))
    enchant_ids = list(map(int, ENCHANT_TAG_RE.findall(markup)))
    return item_ids, spell_ids, enchant_ids


def process_file(
    path: pathlib.Path,
    items_only: bool,
) -> dict:
    """Process one HTML file; return dict with markup and/or extracted IDs."""
    text = path.read_text(encoding="utf-8", errors="replace")
    payload = extract_print_html_payload(text)
    if not payload:
        return {"path": str(path), "markup_found": False}

    item_ids, spell_ids, enchant_ids = extract_ids_from_markup(payload)
    out: dict = {
        "path": str(path),
        "markup_found": True,
        "item_ids": list(dict.fromkeys(item_ids)),
        "spell_ids": list(dict.fromkeys(spell_ids)),
        "enchant_ids": list(dict.fromkeys(enchant_ids)),
    }
    if not items_only:
        out["markup_length"] = len(payload)
        out["markup_preview"] = payload[:500].replace("\r\n", "\n").replace("\n", " ")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract guide body markup and item/spell IDs from Wowhead guide HTML."
    )
    parser.add_argument(
        "path",
        type=pathlib.Path,
        help="Path to a single .html file or a directory of HTML files.",
    )
    parser.add_argument(
        "--items-only",
        action="store_true",
        help="Only output item/spell/enchant ID lists; no markup preview.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output one JSON object per file (or one combined list) to stdout.",
    )
    args = parser.parse_args()

    path = args.path.resolve()
    if not path.exists():
        print(f"Error: path does not exist: {path}", file=sys.stderr)
        return 1

    if path.is_file():
        files = [path] if path.suffix.lower() == ".html" else []
    else:
        files = sorted(path.rglob("*.html"))

    if not files:
        print("No HTML files found.", file=sys.stderr)
        return 1

    results = []
    for f in files:
        try:
            results.append(process_file(f, args.items_only))
        except Exception as e:
            results.append({"path": str(f), "error": str(e)})

    if args.json:
        print(json.dumps(results if len(results) != 1 else results[0], indent=2))
    else:
        for r in results:
            print(f"\n--- {r['path']} ---")
            if r.get("markup_found"):
                print(f"  Items: {len(r.get('item_ids', []))} unique")
                print(f"  Spells: {len(r.get('spell_ids', []))} unique")
                print(f"  Enchants: {len(r.get('enchant_ids', []))} unique")
                if not args.items_only and "markup_preview" in r:
                    print(f"  Preview: {r['markup_preview'][:200]}...")
            else:
                print("  No WH.markup.printHtml payload found (not a guide page or layout changed).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
