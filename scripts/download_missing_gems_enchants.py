#!/usr/bin/env python3
"""Download missing Wowhead TBC Gems & Enchants guides."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Set

try:
    from .download_missing_guides import (
        extract_title,
        http_get,
        list_tbc_guide_urls_from_sitemap,
        save_html,
    )
except ImportError:
    from download_missing_guides import extract_title, http_get, list_tbc_guide_urls_from_sitemap, save_html


SPEC_ALIASES = {
    "Balance Druid DPS": ["druid", "balance", "dps"],
    "Beast Mastery Hunter DPS": ["hunter", "dps"],
    "Feral Druid Tank": ["druid", "feral", "tank"],
    "Restoration Druid Healing": ["druid", "healer"],
    "Restoration Shaman Healing": ["shaman", "healer"],
    "Retribution Paladin DPS": ["paladin", "retribution", "dps"],
    "Rogue DPS": ["rogue", "dps"],
    "Survival Hunter DPS": ["hunter", "dps"],
}


def specs_missing_gems(coverage_json: Dict) -> List[str]:
    phase_rows = coverage_json.get("coverage", {}).get("phase_coverage", [])
    specs = sorted({row["spec"] for row in phase_rows})

    covered: Set[str] = set()
    for guide in coverage_json.get("guides", []):
        if guide.get("guide_type") != "gems_enchants":
            continue
        for spec in guide.get("applies_to_specs", [guide.get("spec")]):
            covered.add(spec)

    return [s for s in specs if s not in covered]


def candidate_urls_from_sitemap(urls: List[str]) -> List[str]:
    return [u for u in urls if "enchants-gems-pve" in u.lower()]


def matches_spec(url: str, spec: str) -> bool:
    lu = url.lower()
    terms = SPEC_ALIASES.get(spec, [w.lower() for w in spec.split()])
    return all(t in lu for t in terms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download missing Gems & Enchants guides from Wowhead sitemap.")
    here = Path(__file__).resolve().parent
    parser.add_argument("--coverage-json", type=Path, default=here / "batch_extracted_items.json")
    parser.add_argument("--dest-dir", type=Path, default=here)
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    coverage = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    missing = specs_missing_gems(coverage)
    if not missing:
        print("No specs missing Gems & Enchants coverage.")
        return 0

    urls = candidate_urls_from_sitemap(list_tbc_guide_urls_from_sitemap())
    print(f"Missing specs: {len(missing)}")
    print(f"Sitemap gems/enchants candidates: {len(urls)}")

    downloaded = 0
    failed: List[str] = []
    for spec in missing:
        matches = [u for u in urls if matches_spec(u, spec)]
        if not matches:
            failed.append(f"{spec}: no matching sitemap URL")
            continue
        chosen = matches[0]
        if args.dry_run:
            print(f"[dry-run] {spec} -> {chosen}")
            continue
        time.sleep(args.delay)
        html = http_get(chosen)
        title = (extract_title(html) or "").lower()
        if "gem" not in title or "enchant" not in title:
            failed.append(f"{spec}: title mismatch ({chosen})")
            continue
        saved = save_html(args.dest_dir, html, f"{spec} Gems and Enchants Guide")
        downloaded += 1
        print(f"[ok] {spec} -> {saved.name}")

    print(f"\nDownloaded: {downloaded}")
    print(f"Failed: {len(failed)}")
    for line in failed:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
