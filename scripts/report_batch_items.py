#!/usr/bin/env python3
"""Print human-readable summaries for batch_extracted_items.json."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Tuple

PHASE_ORDER = ["PRE_RAID", "P1", "P2", "P3", "P4", "P5", "ALL"]
EXPECTED_SLOTS = [
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
    "Main-Hand",
    "Off-Hand",
    "Ranged",
    "Totems",
    "Idols",
    "Librams",
]


def phase_key(phase: str) -> Tuple[int, str]:
    try:
        return (PHASE_ORDER.index(phase), phase)
    except ValueError:
        return (len(PHASE_ORDER), phase)


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Summarize specs/phases/slots in a batch_extracted_items.json file."
    )
    parser.add_argument(
        "input_json",
        nargs="?",
        default=here / "batch_extracted_items.json",
        type=Path,
        help="Path to batch_extracted_items.json",
    )
    parser.add_argument(
        "--spec",
        help="Only show one spec (case-insensitive exact match)",
    )
    parser.add_argument(
        "--show-empty",
        action="store_true",
        help="Print slots with zero items as well",
    )
    return parser.parse_args()


def slot_item_counts(slots: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for slot_entry in slots:
        slot_name = slot_entry.get("slot", "<unknown>")
        items = slot_entry.get("items") or []
        counts[slot_name] = len(items)
    return counts


def print_global_summary(guides: List[Dict[str, Any]]) -> None:
    specs = sorted({g.get("spec", "<unknown>") for g in guides})
    phases = sorted({g.get("phase", "<unknown>") for g in guides}, key=phase_key)
    parse_errors = [g for g in guides if g.get("parse_error")]

    slot_counts = [g.get("slot_count", 0) for g in guides]
    item_counts = [g.get("item_count", 0) for g in guides]

    print("=== Global Summary ===")
    print(f"Guides: {len(guides)}")
    print(f"Specs: {len(specs)}")
    print(f"Phases: {', '.join(phases)}")
    print(f"Parse errors: {len(parse_errors)}")
    if slot_counts:
        print(
            "Slot count per guide: "
            f"min={min(slot_counts)} median={int(median(slot_counts))} max={max(slot_counts)}"
        )
    if item_counts:
        print(
            "Item count per guide: "
            f"min={min(item_counts)} median={int(median(item_counts))} max={max(item_counts)}"
        )

    bad_guides = [
        g
        for g in guides
        if g.get("guide_type") == "bis" and g.get("phase") != "ALL" and g.get("slot_count", 0) <= 1
    ]
    if bad_guides:
        print("Potentially broken BIS guides (slot_count <= 1):")
        for g in sorted(bad_guides, key=lambda x: (x.get("spec", ""), phase_key(x.get("phase", "")))):
            print(f"  - {g.get('spec')} {g.get('phase')} ({g.get('file')})")
    print()


def print_spec_phase_breakdown(guides: List[Dict[str, Any]], show_empty: bool) -> None:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for guide in guides:
        grouped[(guide.get("spec", "<unknown>"), guide.get("phase", "<unknown>"))].append(guide)

    specs = sorted({k[0] for k in grouped.keys()})

    print("=== Spec / Phase Slot Counts ===")
    for spec in specs:
        print(f"\n## {spec}")
        spec_rows = [(phase, grouped[(spec, phase)]) for (s, phase) in grouped.keys() if s == spec]
        for phase, phase_guides in sorted(spec_rows, key=lambda x: phase_key(x[0])):
            all_slot_counts: Counter[str] = Counter()
            files = []
            parse_errors = 0
            unparsed_headers = 0
            total_items = 0
            total_slots = 0
            expected_missing = set(EXPECTED_SLOTS)

            for guide in phase_guides:
                files.append(guide.get("file", "<unknown file>"))
                if guide.get("parse_error"):
                    parse_errors += 1
                unparsed_headers += len(guide.get("unparsed_slot_like_headers") or [])
                total_items += guide.get("item_count", 0)
                total_slots += guide.get("slot_count", 0)

                s_counts = slot_item_counts(guide.get("slots") or [])
                all_slot_counts.update(s_counts)
                expected_missing -= set(s_counts.keys())

            print(
                f"  - {phase}: guides={len(phase_guides)} slots={total_slots} items={total_items} "
                f"parse_errors={parse_errors} unparsed_slot_headers={unparsed_headers}"
            )

            ordered_slots = [s for s in EXPECTED_SLOTS if s in all_slot_counts]
            ordered_slots += sorted([s for s in all_slot_counts if s not in EXPECTED_SLOTS])
            for slot in ordered_slots:
                count = all_slot_counts[slot]
                if count == 0 and not show_empty:
                    continue
                print(f"      {slot:10s} {count}")

            if expected_missing:
                print(f"      missing_expected_slots: {', '.join(sorted(expected_missing))}")

            if len(phase_guides) > 1:
                print("      source_files:")
                for f in files:
                    print(f"        - {f}")


def main() -> int:
    args = parse_args()
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    guides = payload.get("guides") if isinstance(payload, dict) else None
    if not isinstance(guides, list):
        raise SystemExit("Input JSON must have top-level object with a 'guides' list")

    if args.spec:
        spec_lookup = {g.get("spec", ""): g.get("spec", "") for g in guides}
        wanted = next((name for name in spec_lookup if name.lower() == args.spec.lower()), None)
        if not wanted:
            raise SystemExit(f"Spec not found: {args.spec}")
        guides = [g for g in guides if g.get("spec") == wanted]

    print_global_summary(guides)
    print_spec_phase_breakdown(guides, show_empty=args.show_empty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
