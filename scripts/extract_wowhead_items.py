#!/usr/bin/env python3
"""Extract WoWhead guide item rankings grouped by slot from saved HTML."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PRINT_HTML_RE = re.compile(
    r"WH\.markup\.printHtml\(\s*(\"(?:\\.|[^\"\\])*\")\s*(?:,|\))", re.DOTALL
)
ADD_DATA_RE = re.compile(r"WH\.Gatherer\.addData\(3,\s*5,\s*(\{.*?\})\);", re.DOTALL)
H3_RE = re.compile(r"\[h3[^\]]*toc=\"([^\"]+)\"[^\]]*\].*?\[/h3\]", re.IGNORECASE | re.DOTALL)
H4_RE = re.compile(r"\[h4[^\]]*\](.*?)\[/h4\]", re.IGNORECASE | re.DOTALL)
TABLE_RE = re.compile(r"\[table[^\]]*\](.*?)\[/table\]", re.IGNORECASE | re.DOTALL)
TR_RE = re.compile(r"\[tr\](.*?)\[/tr\]", re.IGNORECASE | re.DOTALL)
TD_RE = re.compile(r"\[td[^\]]*\](.*?)\[/td\]", re.IGNORECASE | re.DOTALL)
ITEM_RE = re.compile(r"\[item=(\d+)\]", re.IGNORECASE)
REF_RE = re.compile(r"\[(item|spell)=(\d+)\]", re.IGNORECASE)
TAG_RE = re.compile(r"\[[^\]]+\]")
WS_RE = re.compile(r"\s+")


def normalize_slot(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"\s+for\s+.+$", "", cleaned, flags=re.IGNORECASE)
    cleaned = WS_RE.sub(" ", cleaned).strip()
    alias = {
        "shoulder": "Shoulders",
        "shoulders": "Shoulders",
        "back": "Back",
        "chest": "Chest",
        "wrist": "Wrist",
        "wrists": "Wrist",
        "hands": "Hands",
        "hand": "Hands",
        "waist": "Waist",
        "legs": "Legs",
        "feet": "Feet",
        "neck": "Neck",
        "head": "Head",
        "ring": "Rings",
        "rings": "Rings",
        "finger": "Rings",
        "fingers": "Rings",
        "trinket": "Trinkets",
        "trinkets": "Trinkets",
        "weapon": "Weapons",
        "weapons": "Weapons",
        "1-handed weapon": "Weapons",
        "1-handed weapons": "Weapons",
        "1handed weapon": "Weapons",
        "1handed weapons": "Weapons",
        "one-handed weapon": "Weapons",
        "one-handed weapons": "Weapons",
        "1h weapons": "Main-Hand",
        "2h weapons": "Main-Hand",
        "off-hand": "Off-Hand",
        "off-hands": "Off-Hand",
        "off hand": "Off-Hand",
        "offhands": "Off-Hand",
        "offhands and shields": "Off-Hand",
        "off-hands and shields": "Off-Hand",
        "shields / off-hands": "Off-Hand",
        "shields & offhands": "Off-Hand",
        "shields & offhands": "Off-Hand",
        "main-hand": "Main-Hand",
        "main hand": "Main-Hand",
        "main-hands": "Main-Hand",
        "totem": "Totems",
        "totems": "Totems",
        "idol": "Idols",
        "idols": "Idols",
        "libram": "Librams",
        "librams": "Librams",
        "ranged": "Ranged",
    }
    key = cleaned.lower()
    return alias.get(key, cleaned)


VALID_SLOTS = {
    "Head",
    "Shoulders",
    "Back",
    "Chest",
    "Wrist",
    "Hands",
    "Waist",
    "Legs",
    "Feet",
    "Neck",
    "Rings",
    "Trinkets",
    "Weapons",
    "Off-Hand",
    "Main-Hand",
    "Totems",
    "Idols",
    "Librams",
    "Ranged",
}

ENHANCEMENT_SLOT_ALIASES = {
    "head enchant": "Head",
    "shoulder enchant": "Shoulders",
    "cloak enchant": "Back",
    "chest enchant": "Chest",
    "bracer enchant": "Wrist",
    "gloves enchant": "Hands",
    "legs enchant": "Legs",
    "leg enchant": "Legs",
    "boots enchant": "Feet",
    "weapon enchant": "Weapons",
    "main-hand enchant": "Main-Hand",
    "off-hand enchant": "Off-Hand",
    "rings enchant": "Rings",
    "ring enchant": "Rings",
}

GEM_GROUP_ALIASES = {
    "best meta": "Meta",
    "best meta gems": "Meta",
    "meta gem": "Meta",
    "meta gems": "Meta",
    "best red": "Red",
    "best red gems": "Red",
    "red gem": "Red",
    "red gems": "Red",
    "best yellow": "Yellow",
    "best yellow gems": "Yellow",
    "yellow gem": "Yellow",
    "yellow gems": "Yellow",
    "best blue": "Blue",
    "best blue gems": "Blue",
    "blue gem": "Blue",
    "blue gems": "Blue",
}

VALID_ENHANCEMENT_BUCKETS = {"Meta", "Red", "Yellow", "Blue", *VALID_SLOTS}


def clean_text(text: str) -> str:
    no_tags = TAG_RE.sub("", text)
    return WS_RE.sub(" ", no_tags).strip()


def extract_markup(html_text: str) -> str:
    match = PRINT_HTML_RE.search(html_text)
    if not match:
        raise ValueError("Could not find WH.markup.printHtml content")
    return json.loads(match.group(1))


def extract_item_lookup(html_text: str) -> Dict[str, str]:
    match = ADD_DATA_RE.search(html_text)
    if not match:
        return {}
    data = json.loads(match.group(1))
    lookup: Dict[str, str] = {}
    for item_id, payload in data.items():
        name = payload.get("name_enus") or payload.get("name")
        if name:
            lookup[str(item_id)] = name
    return lookup


def _normalize_enhancement_bucket(raw: str) -> str:
    cleaned = WS_RE.sub(" ", raw.strip()).strip().lower()
    if cleaned in GEM_GROUP_ALIASES:
        return GEM_GROUP_ALIASES[cleaned]
    if cleaned in ENHANCEMENT_SLOT_ALIASES:
        return ENHANCEMENT_SLOT_ALIASES[cleaned]
    # Fallback to slot normalization so aliases like "off hand enchant" still map.
    if cleaned.endswith(" enchant"):
        maybe_slot = normalize_slot(cleaned[:-8])
        if maybe_slot in VALID_SLOTS:
            return maybe_slot
    return raw.strip()


def _extract_inline_refs(section: str, item_lookup: Dict[str, str]) -> List[Dict[str, Any]]:
    seen: set[tuple[str, int]] = set()
    items: List[Dict[str, Any]] = []
    order = 1
    for match in REF_RE.finditer(section):
        ref_type = match.group(1).lower()
        ref_id = int(match.group(2))
        key = (ref_type, ref_id)
        if key in seen:
            continue
        seen.add(key)

        row: Dict[str, Any] = {
            "order": order,
            "rank": "Best" if order == 1 else "Alternative",
            "source": "",
            "tie_group_size": 1,
            "tie_group_index": 1,
            "tie_with_previous": False,
            "ref_type": ref_type,
            "ref_id": ref_id,
        }
        if ref_type == "item":
            row["item_id"] = ref_id
            row["item_name"] = item_lookup.get(str(ref_id))
        else:
            row["spell_id"] = ref_id
        items.append(row)
        order += 1
    return items


def extract_by_slot(markup: str, item_lookup: Dict[str, str], guide_type: str = "bis") -> List[Dict[str, Any]]:
    # Some guides use [h3 toc="Body Armor"] + nested [h4]Head[/h4]-style slot sections.
    # Include both h3(toc) and h4 headers, then keep only normalized valid slots.
    headers: List[tuple[int, int, str]] = []
    for m in H3_RE.finditer(markup):
        headers.append((m.start(), m.end(), m.group(1)))
    for m in H4_RE.finditer(markup):
        headers.append((m.start(), m.end(), clean_text(m.group(1))))
    headers.sort(key=lambda x: x[0])

    results: List[Dict[str, Any]] = []

    for i, header in enumerate(headers):
        _, header_end, header_name = header
        if guide_type == "gems_enchants":
            slot_name = _normalize_enhancement_bucket(header_name)
            valid_slots = VALID_ENHANCEMENT_BUCKETS
        else:
            slot_name = normalize_slot(header_name)
            valid_slots = VALID_SLOTS
        if slot_name not in valid_slots:
            continue
        section_start = header_end
        section_end = headers[i + 1][0] if i + 1 < len(headers) else len(markup)
        section = markup[section_start:section_end]

        items: List[Dict[str, Any]] = []
        row_order = 1

        for table_block in TABLE_RE.finditer(section):
            table_body = table_block.group(1)
            for row_match in TR_RE.finditer(table_body):
                cells = TD_RE.findall(row_match.group(1))
                if len(cells) < 2:
                    continue

                item_ids = ITEM_RE.findall(cells[1])
                if not item_ids:
                    continue

                rank_text = clean_text(cells[0])
                if not rank_text or rank_text.lower() == "rank":
                    continue

                source = clean_text(cells[2]) if len(cells) >= 3 else ""
                tie_group_size = len(item_ids)

                for tie_index, item_id in enumerate(item_ids, start=1):
                    item_name = item_lookup.get(item_id)
                    items.append(
                        {
                            "order": row_order,
                            "rank": rank_text,
                            "item_id": int(item_id),
                            "item_name": item_name,
                            "source": source,
                            "tie_group_size": tie_group_size,
                            "tie_group_index": tie_index,
                            "tie_with_previous": tie_index > 1,
                            "ref_type": "item",
                            "ref_id": int(item_id),
                        }
                    )
                row_order += 1

        if not items and guide_type == "gems_enchants":
            items = _extract_inline_refs(section, item_lookup)

        if items:
            results.append({"slot": slot_name, "items": items})

    return results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract ranked WoWhead guide items grouped by slot from a saved HTML file."
    )
    parser.add_argument("input_html", type=Path, help="Path to saved Wowhead guide HTML")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON file (default: stdout)")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    parser.add_argument(
        "--guide-type",
        choices=["bis", "gems_enchants"],
        default="bis",
        help="Guide type controls extraction strategy.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    try:
        html_text = args.input_html.read_text(encoding="utf-8")
        markup = extract_markup(html_text)
        item_lookup = extract_item_lookup(html_text)
        grouped = extract_by_slot(markup, item_lookup, guide_type=args.guide_type)
    except Exception as exc:  # pragma: no cover
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    payload = {
        "source_file": str(args.input_html),
        "slots": grouped,
        "total_slots": len(grouped),
        "total_items": sum(len(slot["items"]) for slot in grouped),
    }

    indent = 2 if args.pretty else None
    output_text = json.dumps(payload, indent=indent, ensure_ascii=True)

    if args.output:
        args.output.write_text(output_text + "\n", encoding="utf-8")
    else:
        print(output_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
