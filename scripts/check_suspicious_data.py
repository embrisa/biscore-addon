#!/usr/bin/env python3
"""Flag suspicious BiScore guide parsing results for manual review."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Dict, List, Tuple

from parse_wowhead_html import build_spec_phase_paths, merge_slot_maps, parse_guide_slots


CORE_SLOTS = {1, 3, 5, 7, 10, 16}


def summarize_phase(slot_map: Dict[int, List[int]]) -> Tuple[int, int, int]:
    slot_count = len(slot_map)
    ranked_total = sum(len(v) for v in slot_map.values())
    singleton_slots = sum(1 for v in slot_map.values() if len(v) <= 1)
    return slot_count, ranked_total, singleton_slots


def check_spec(
    spec_blob: Dict,
    downloads_root: pathlib.Path,
    min_slot_count: int,
    max_slot_drop: int,
    max_rank_drop_pct: float,
) -> List[Dict]:
    findings: List[Dict] = []
    phase_paths = build_spec_phase_paths(spec_blob)
    covered_specs = spec_blob.get("covered_specs", [])
    phase_maps: Dict[int, Dict[int, List[int]]] = {}

    prev_slot_map: Dict[int, List[int]] = {}
    for phase in range(1, 6):
        rel = phase_paths.get(phase)
        if not rel:
            findings.append(
                {
                    "severity": "high",
                    "type": "missing_phase_file",
                    "phase": phase,
                    "detail": "No guide file mapped for this phase",
                }
            )
            continue
        full = downloads_root / rel
        if not full.exists():
            findings.append(
                {
                    "severity": "high",
                    "type": "missing_phase_html",
                    "phase": phase,
                    "detail": f"Missing HTML file: {rel}",
                }
            )
            continue

        slot_map = parse_guide_slots(full)
        if phase > 1:
            slot_map = merge_slot_maps(prev_slot_map, slot_map)
        phase_maps[phase] = slot_map
        prev_slot_map = slot_map
        slots, ranked_total, singleton = summarize_phase(slot_map)
        if slots == 0:
            findings.append(
                {
                    "severity": "high",
                    "type": "empty_phase_parse",
                    "phase": phase,
                    "detail": f"0 parsed slots from {rel}",
                }
            )
        elif slots < min_slot_count:
            findings.append(
                {
                    "severity": "medium",
                    "type": "low_slot_coverage",
                    "phase": phase,
                    "detail": f"{slots} slots (< {min_slot_count})",
                }
            )

        if slots > 0 and (singleton / slots) >= 0.6:
            findings.append(
                {
                    "severity": "low",
                    "type": "many_singleton_slots",
                    "phase": phase,
                    "detail": f"{singleton}/{slots} slots have only 1 ranked item",
                }
            )
        if phase == 5 and not CORE_SLOTS.issubset(set(slot_map.keys())):
            missing = sorted(CORE_SLOTS - set(slot_map.keys()))
            findings.append(
                {
                    "severity": "medium",
                    "type": "missing_core_slots_p5",
                    "phase": 5,
                    "detail": f"Missing core slots in P5: {missing}",
                }
            )

    for phase in range(2, 6):
        prev = phase_maps.get(phase - 1, {})
        curr = phase_maps.get(phase, {})
        if not prev or not curr:
            continue
        prev_slots, prev_ranks, _ = summarize_phase(prev)
        curr_slots, curr_ranks, _ = summarize_phase(curr)

        if prev_slots - curr_slots > max_slot_drop:
            findings.append(
                {
                    "severity": "medium",
                    "type": "slot_drop_between_phases",
                    "phase": phase,
                    "detail": f"Slots dropped {prev_slots} -> {curr_slots}",
                }
            )

        if prev_ranks > 0:
            drop_pct = (prev_ranks - curr_ranks) / prev_ranks
            if drop_pct > max_rank_drop_pct:
                findings.append(
                    {
                        "severity": "medium",
                        "type": "ranked_item_drop_between_phases",
                        "phase": phase,
                        "detail": f"Ranked items dropped {prev_ranks} -> {curr_ranks} ({drop_pct:.1%})",
                    }
                )

    if findings:
        return [
            {
                "spec_key": spec_blob.get("spec_key"),
                "covered_specs": covered_specs,
                "findings": findings,
            }
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Check generated BiScore data for suspicious patterns.")
    parser.add_argument("--manifest", default="downloads/wowhead_tbc_bis/manifest.json")
    parser.add_argument("--downloads-root", default="downloads/wowhead_tbc_bis")
    parser.add_argument("--min-slot-count", type=int, default=14)
    parser.add_argument("--max-slot-drop", type=int, default=2)
    parser.add_argument("--max-rank-drop-pct", type=float, default=0.35)
    parser.add_argument("--only-class", default=None, help="Filter by class slug in spec_key, e.g. paladin")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    manifest_path = pathlib.Path(args.manifest)
    downloads_root = pathlib.Path(args.downloads_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    out: List[Dict] = []
    for spec_blob in manifest.get("specs", []):
        spec_key = str(spec_blob.get("spec_key", ""))
        if args.only_class and not spec_key.startswith(args.only_class + "-"):
            continue
        out.extend(
            check_spec(
                spec_blob=spec_blob,
                downloads_root=downloads_root,
                min_slot_count=args.min_slot_count,
                max_slot_drop=args.max_slot_drop,
                max_rank_drop_pct=args.max_rank_drop_pct,
            )
        )

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    if not out:
        print("No suspicious entries found.")
        return 0

    print(f"Suspicious spec entries: {len(out)}")
    for item in out:
        print(f"\n[{item['spec_key']}] covered={item['covered_specs']}")
        for finding in item["findings"]:
            print(f"  - {finding['severity']}: {finding['type']} (phase {finding['phase']}) -> {finding['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
