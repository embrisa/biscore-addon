#!/usr/bin/env python3
"""Batch-extract Wowhead guide data and generate coverage reports."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .extract_wowhead_items import (
        H3_RE,
        extract_by_slot,
        extract_item_lookup,
        extract_markup,
        normalize_slot,
    )
except ImportError:
    from extract_wowhead_items import (
        H3_RE,
        extract_by_slot,
        extract_item_lookup,
        extract_markup,
        normalize_slot,
    )

PHASE_ORDER = ["PRE_RAID", "P1", "P2", "P3", "P4", "P5"]

EXPECTED_SLOTS = {
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
    "Ranged",
    "Totems",
    "Idols",
    "Librams",
}

SLOT_HINT_RE = re.compile(
    r"(head|helm|shoulder|back|cloak|chest|wrist|bracer|hand|glove|waist|belt|leg|feet|boot|neck|ring|trinket|weapon|off[- ]?hand|main[- ]?hand|ranged|totem|idol|libram)",
    re.IGNORECASE,
)

HEADER_PATTERNS = {
    "gems": re.compile(r"\bgem[s]?\b", re.IGNORECASE),
    "enchants": re.compile(r"\benchant[s]?\b", re.IGNORECASE),
    "stat_weights": re.compile(r"stat (weights?|priority|scaling)", re.IGNORECASE),
    "overrides": re.compile(r"\b(override[s]?|special (?:items?|cases?)|proc(?:s)?)\b", re.IGNORECASE),
}


def parse_guide_name(filename: str) -> Optional[Dict[str, str]]:
    name = filename.replace(" - Wowhead.html", "")
    lower = name.lower()

    phase_match = re.match(
        r"Burning Crusade Classic (.+?) Best in Slot \(BiS\) Phase ([1-5])",
        name,
    )
    if phase_match:
        return {
            "spec": phase_match.group(1).strip(),
            "phase": f"P{phase_match.group(2)}",
            "guide_type": "bis",
        }

    p1_match = re.match(r"(.+?) Phase ([1-5]) Best in Slot \(BiS\)", name)
    if p1_match:
        return {
            "spec": p1_match.group(1).strip(),
            "phase": f"P{p1_match.group(2)}",
            "guide_type": "bis",
        }

    prepatch_match = re.match(r"(.+?) Pre-Patch Best in Slot", name, re.IGNORECASE)
    if prepatch_match:
        return {
            "spec": prepatch_match.group(1).strip(),
            "phase": "P1",
            "guide_type": "bis",
        }

    if "best in slot" in lower:
        lead = re.match(r"(.+?) (?:DPS|Healing|Healer|Tank)", name, re.IGNORECASE)
        if lead:
            role_word = re.search(r"(DPS|Healing|Healer|Tank)", name, re.IGNORECASE)
            if role_word:
                role = role_word.group(1)
                role = "Healing" if role.lower() == "healer" else role
                spec = f"{lead.group(1).strip()} {role}"
                if "karazhan" in lower:
                    return {"spec": spec, "phase": "P1", "guide_type": "bis"}
                if "phase 2" in lower:
                    return {"spec": spec, "phase": "P2", "guide_type": "bis"}
                if "bt" in lower and "hyjal" in lower:
                    return {"spec": spec, "phase": "P3", "guide_type": "bis"}
                if "za" in lower or "zul-aman" in lower:
                    return {"spec": spec, "phase": "P4", "guide_type": "bis"}
                if "swp" in lower or "sunwell" in lower or "phase 5" in lower:
                    return {"spec": spec, "phase": "P5", "guide_type": "bis"}

    pre_match = re.match(r"(.+?) Pre-Raid Best(?: in |\-in\-)?Slot \(BiS\)", name, re.IGNORECASE)
    if pre_match:
        return {
            "spec": pre_match.group(1).strip(),
            "phase": "PRE_RAID",
            "guide_type": "bis",
        }

    gems_match = re.match(r"(?:TBC )?(.+?) Gems (?:&|and) Enchants Guide", name, re.IGNORECASE)
    if gems_match:
        return {
            "spec": gems_match.group(1).strip(),
            "phase": "ALL",
            "guide_type": "gems_enchants",
        }

    return None


def extract_headers(markup: str) -> List[str]:
    return [m.group(1).strip() for m in H3_RE.finditer(markup)]


def detect_slot_like_unparsed(headers: List[str], parsed_slots: Set[str]) -> List[str]:
    unparsed: List[str] = []
    for header in headers:
        norm = normalize_slot(header)
        if SLOT_HINT_RE.search(header) and norm not in parsed_slots:
            unparsed.append(header)
    return sorted(set(unparsed))


def detect_data_types(headers: List[str], guide_type: str) -> Dict[str, bool]:
    joined_headers = "\n".join(headers)
    detected = {name: bool(pattern.search(joined_headers)) for name, pattern in HEADER_PATTERNS.items()}
    if guide_type == "gems_enchants":
        detected["gems"] = True
        detected["enchants"] = True
    return detected


def expand_spec_targets(spec: str, guide_type: str) -> List[str]:
    if guide_type != "gems_enchants":
        return [spec]
    if spec == "Warlock DPS":
        return ["Affliction Warlock DPS", "Demonology Warlock DPS", "Destruction Warlock DPS"]
    if spec == "Mage DPS":
        return ["Arcane Mage DPS", "Fire Mage DPS", "Frost Mage DPS"]
    if spec == "Hunter DPS":
        return ["Beast Mastery Hunter DPS", "Marksmanship Hunter DPS", "Survival Hunter DPS"]
    if spec == "Priest DPS":
        return ["Shadow Priest DPS"]
    if spec == "Warrior DPS":
        return ["Arms Warrior DPS", "Fury Warrior DPS"]
    return [spec]


def load_guides(input_dir: Path) -> List[Dict[str, Any]]:
    guides: List[Dict[str, Any]] = []

    for html_path in sorted(input_dir.glob("*.html")):
        parsed = parse_guide_name(html_path.name)
        if not parsed:
            continue

        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        try:
            markup = extract_markup(html_text)
            item_lookup = extract_item_lookup(html_text)
            slots = extract_by_slot(markup, item_lookup, guide_type=parsed["guide_type"])
            headers = extract_headers(markup)
        except Exception as exc:
            guides.append(
                {
                    **parsed,
                    "applies_to_specs": expand_spec_targets(parsed["spec"], parsed["guide_type"]),
                    "file": html_path.name,
                    "parse_error": str(exc),
                    "slots": [],
                    "slot_count": 0,
                    "item_count": 0,
                    "missing_expected_slots": sorted(EXPECTED_SLOTS),
                    "unparsed_slot_like_headers": [],
                    "data_types_detected": {
                        "gems": False,
                        "enchants": False,
                        "stat_weights": False,
                        "overrides": False,
                    },
                }
            )
            continue

        parsed_slots = {entry["slot"] for entry in slots}
        missing_expected = sorted(EXPECTED_SLOTS - parsed_slots)
        unparsed_slot_like = detect_slot_like_unparsed(headers, parsed_slots)
        detected = detect_data_types(headers, parsed["guide_type"])
        item_count = sum(len(s["items"]) for s in slots)

        guides.append(
            {
                **parsed,
                "applies_to_specs": expand_spec_targets(parsed["spec"], parsed["guide_type"]),
                "file": html_path.name,
                "parse_error": None,
                "slots": slots,
                "slot_count": len(slots),
                "item_count": item_count,
                "missing_expected_slots": missing_expected,
                "unparsed_slot_like_headers": unparsed_slot_like,
                "data_types_detected": detected,
            }
        )
    return guides


def summarize_coverage(guides: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_spec_phase: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    spec_data_guides: Dict[str, Dict[str, bool]] = defaultdict(
        lambda: {"gems": False, "enchants": False, "stat_weights": False, "overrides": False}
    )
    specs: Set[str] = set()

    for guide in guides:
        specs.update(guide["applies_to_specs"])
        if guide["phase"] in PHASE_ORDER:
            by_spec_phase[(guide["spec"], guide["phase"])].append(guide)
            for key, val in guide["data_types_detected"].items():
                spec_data_guides[guide["spec"]][key] = spec_data_guides[guide["spec"]][key] or val
        else:
            for target_spec in guide["applies_to_specs"]:
                for key, val in guide["data_types_detected"].items():
                    spec_data_guides[target_spec][key] = spec_data_guides[target_spec][key] or val

    phase_rows: List[Dict[str, Any]] = []
    for spec in sorted(specs):
        for phase in PHASE_ORDER:
            entries = by_spec_phase.get((spec, phase), [])
            bis = [g for g in entries if g["guide_type"] == "bis"]
            bis_exists = len(bis) > 0
            slot_count = bis[0]["slot_count"] if bis_exists else 0
            missing_slots = bis[0]["missing_expected_slots"] if bis_exists else sorted(EXPECTED_SLOTS)

            data_presence = {
                "bis_slots": bis_exists and slot_count > 0,
                "gems": spec_data_guides[spec]["gems"],
                "enchants": spec_data_guides[spec]["enchants"],
                "stat_weights": spec_data_guides[spec]["stat_weights"],
                "overrides": spec_data_guides[spec]["overrides"],
            }
            missing_data_types = sorted([k for k, v in data_presence.items() if not v])

            phase_rows.append(
                {
                    "spec": spec,
                    "phase": phase,
                    "bis_guide_found": bis_exists,
                    "slot_count": slot_count,
                    "missing_expected_slots": missing_slots,
                    "missing_data_types": missing_data_types,
                }
            )

    return {
        "spec_count": len(specs),
        "guide_count": len(guides),
        "phase_coverage": phase_rows,
    }


def render_report(guides: List[Dict[str, Any]], coverage: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Wowhead Guide Coverage Report")
    lines.append("")
    lines.append(f"- Total guides parsed: {coverage['guide_count']}")
    lines.append(f"- Total specs discovered: {coverage['spec_count']}")
    lines.append("")
    lines.append("## Spec/Phase Completeness")
    lines.append("")
    lines.append("| Spec | Phase | BiS Guide | Slots | Missing Data Types |")
    lines.append("|---|---|---:|---:|---|")

    for row in coverage["phase_coverage"]:
        lines.append(
            f"| {row['spec']} | {row['phase']} | "
            f"{'yes' if row['bis_guide_found'] else 'no'} | {row['slot_count']} | "
            f"{', '.join(row['missing_data_types']) if row['missing_data_types'] else 'none'} |"
        )

    lines.append("")
    lines.append("## Guides With Slot Parsing Gaps")
    lines.append("")
    gap_guides = [
        g
        for g in guides
        if g["guide_type"] == "bis"
        and (g["unparsed_slot_like_headers"] or g["parse_error"] is not None)
    ]
    if not gap_guides:
        lines.append("- None detected")
    else:
        for g in gap_guides:
            problems: List[str] = []
            if g["parse_error"]:
                problems.append(f"parse_error={g['parse_error']}")
            if g["unparsed_slot_like_headers"]:
                problems.append(f"unparsed_headers={', '.join(g['unparsed_slot_like_headers'])}")
            lines.append(f"- `{g['file']}`: {'; '.join(problems)}")

    lines.append("")
    lines.append("## Guide Data-Type Detection")
    lines.append("")
    lines.append("| File | Type | Gems | Enchants | Stat Weights | Overrides |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for g in guides:
        d = g["data_types_detected"]
        lines.append(
            f"| {g['file']} | {g['guide_type']} | "
            f"{'yes' if d['gems'] else 'no'} | {'yes' if d['enchants'] else 'no'} | "
            f"{'yes' if d['stat_weights'] else 'no'} | {'yes' if d['overrides'] else 'no'} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch extract Wowhead guides and generate coverage reports."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory containing saved Wowhead HTML files.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(__file__).resolve().parent / "batch_extracted_items.json",
        help="Output path for aggregated JSON data.",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path(__file__).resolve().parent / "coverage_report.md",
        help="Output path for coverage report Markdown.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    guides = load_guides(args.input_dir)
    coverage = summarize_coverage(guides)

    payload = {
        "guides": guides,
        "coverage": coverage,
    }

    args.output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    args.output_report.write_text(render_report(guides, coverage), encoding="utf-8")

    print(f"Wrote JSON: {args.output_json}")
    print(f"Wrote report: {args.output_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
