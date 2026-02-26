#!/usr/bin/env python3
"""Download missing Wowhead TBC BiS guides from coverage data."""

from __future__ import annotations

import argparse
import json
import re
import time
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

GUIDE_HREF_RE = re.compile(r'href="(/tbc/guide/[^"#?]+)"', re.IGNORECASE)
DDG_HREF_RE = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>', re.IGNORECASE)
SITEMAP_LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.IGNORECASE)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
WS_RE = re.compile(r"\s+")
SAFE_FILE_RE = re.compile(r'[^A-Za-z0-9 _().,\-+&]')
WORD_RE = re.compile(r"[A-Za-z]+")
ROLE_WORDS = {"dps", "healing", "tank"}
SPEC_ALIASES = {
    "Restoration Druid Healing": ["restoration druid healer", "druid healer", "resto druid healer"],
    "Restoration Shaman Healing": ["restoration shaman healer", "shaman healer", "resto shaman healer"],
    "Priest Healing": ["priest healer", "holy priest healer", "discipline priest healer"],
    "Holy Paladin Healing": ["holy paladin healer", "paladin healer"],
}
KNOWN_UNSUPPORTED_SPECS = {
    # No dedicated TBC Wowhead BiS phase pages appear to exist for this spec.
    "Marksmanship Hunter DPS",
}


def http_get(url: str, timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def clean_title(raw: str) -> str:
    text = unescape(raw).strip()
    text = WS_RE.sub(" ", text)
    text = SAFE_FILE_RE.sub("", text)
    return text


def extract_title(html: str) -> Optional[str]:
    m = TITLE_RE.search(html)
    if not m:
        return None
    return clean_title(m.group(1))


def is_incomplete_bis_row(row: Dict, min_slot_count: int) -> bool:
    """Return True when a row is found but clearly incomplete/corrupt."""
    if not row.get("bis_guide_found"):
        return False
    slot_count = int(row.get("slot_count", 0) or 0)
    # Extremely low slot count is a strong signal that extraction latched onto
    # a partial table/section instead of a full BiS page.
    return slot_count < min_slot_count


def missing_phase_rows(
    coverage_json: Dict,
    min_slot_count: int,
    excluded_specs: set[str],
) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for row in coverage_json.get("coverage", {}).get("phase_coverage", []):
        phase = row.get("phase")
        spec = row.get("spec")
        if phase not in {"PRE_RAID", "P1", "P2", "P3", "P4", "P5"} or not spec:
            continue
        if spec in excluded_specs:
            continue
        if row.get("bis_guide_found") and not is_incomplete_bis_row(row, min_slot_count):
            continue
        out.append((spec, phase))
    return out


def query_text(spec: str, phase: str) -> str:
    if phase == "PRE_RAID":
        return f"{spec} Pre-Raid Best in Slot BiS TBC Classic site:wowhead.com/tbc/guide"
    phase_num = phase[1:] if phase.startswith("P") else phase
    return f"{spec} Phase {phase_num} Best in Slot BiS TBC Classic site:wowhead.com/tbc/guide"


def search_wowhead_candidates(spec: str, phase: str) -> List[str]:
    q = quote_plus(query_text(spec, phase))
    search_url = f"https://www.wowhead.com/tbc/search?q={q}"
    html = http_get(search_url)
    hrefs = [urljoin("https://www.wowhead.com", m.group(1)) for m in GUIDE_HREF_RE.finditer(html)]
    # de-duplicate while preserving order
    dedup: List[str] = []
    seen = set()
    for href in hrefs:
        if href in seen:
            continue
        seen.add(href)
        dedup.append(href)
    return dedup


def search_duckduckgo_candidates(spec: str, phase: str) -> List[str]:
    q = quote_plus(query_text(spec, phase))
    search_url = f"https://html.duckduckgo.com/html/?q={q}"
    html = http_get(search_url)
    urls: List[str] = []
    for m in DDG_HREF_RE.finditer(html):
        href = unescape(m.group(1))
        if "wowhead.com/tbc/guide/" not in href.lower():
            continue
        clean = href.split("&rut=")[0]
        urls.append(clean)
    dedup: List[str] = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        dedup.append(u)
    return dedup


def score_candidate(url: str, spec: str, phase: str) -> int:
    s = 0
    u = url.lower()
    spec_words = [w.lower() for w in re.findall(r"[A-Za-z]+", spec)]
    for w in spec_words:
        if w in u:
            s += 2
    if phase == "PRE_RAID":
        if "pre-raid" in u:
            s += 8
    elif phase == "P1":
        if "karazhan" in u:
            s += 10
        if "pre-patch" in u or "pre patch" in u:
            s += 6
        if "pre-raid" in u:
            s -= 6
    else:
        phase_num = phase[1:] if phase.startswith("P") else phase
        if f"phase-{phase_num}" in u or f"phase {phase_num}" in u:
            s += 8
    if "best-in-slot" in u or "bis" in u:
        s += 3
    if "pvp" in u:
        s -= 20
    return s


def core_spec_words(spec: str) -> List[str]:
    alias_texts = SPEC_ALIASES.get(spec, [spec])
    words: List[str] = []
    for text in alias_texts:
        words.extend([w.lower() for w in WORD_RE.findall(text)])
    return [w for w in words if w not in ROLE_WORDS]


def expected_role(spec: str) -> str:
    sl = spec.lower()
    if "healing" in sl:
        return "healer"
    if "tank" in sl:
        return "tank"
    return "dps"


def spec_match_count(text: str, spec: str) -> int:
    t = text.lower()
    words = core_spec_words(spec)
    return sum(1 for w in words if w in t)


def phase_matches_text(text: str, phase: str) -> bool:
    t = text.lower()
    if phase == "PRE_RAID":
        return "pre-raid" in t or "pre patch" in t or "pre-patch" in t
    if phase == "P1":
        return ("phase 1" in t) or ("phase-1" in t) or ("karazhan" in t) or ("pre-patch" in t) or ("pre patch" in t)
    if phase == "P2":
        return ("phase 2" in t) or ("phase-2" in t)
    if phase == "P3":
        return ("phase 3" in t) or ("phase-3" in t) or ("bt-hyjal" in t) or ("black temple" in t and "hyjal" in t)
    if phase == "P4":
        return ("phase 4" in t) or ("phase-4" in t) or ("za" in t) or ("zul-aman" in t)
    if phase == "P5":
        return ("phase 5" in t) or ("phase-5" in t) or ("swp" in t) or ("sunwell" in t)
    return True


def looks_like_expected_guide(url: str, title: str, spec: str, phase: str) -> bool:
    haystack = f"{url} {title}".lower()
    required_word_matches = min(2, max(1, len(core_spec_words(spec))))
    if spec_match_count(haystack, spec) < required_word_matches:
        return False
    if not phase_matches_text(haystack, phase):
        return False
    role = expected_role(spec)
    u = url.lower()
    if role == "healer" and ("healer" not in u and "healing" not in u):
        return False
    if role == "tank" and "tank" not in u:
        return False
    if role == "dps" and "dps" not in u:
        return False
    if "pvp" in haystack:
        return False
    return True


def choose_best_candidate(urls: List[str], spec: str, phase: str) -> Optional[str]:
    if not urls:
        return None
    ranked = sorted(urls, key=lambda u: score_candidate(u, spec, phase), reverse=True)
    return ranked[0]


def filter_sitemap_candidates(urls: List[str], spec: str) -> List[str]:
    role = expected_role(spec)
    class_words = {"druid", "shaman", "mage", "warlock", "rogue", "hunter", "paladin", "priest", "warrior"}
    wanted_classes = [w for w in core_spec_words(spec) if w in class_words]
    out: List[str] = []
    for u in urls:
        lu = u.lower()
        if role == "healer" and ("healer" not in lu and "healing" not in lu):
            continue
        if role == "tank" and "tank" not in lu:
            continue
        if role == "dps" and "dps" not in lu:
            continue
        if wanted_classes and not any(c in lu for c in wanted_classes):
            continue
        out.append(u)
    return out


def list_tbc_guide_urls_from_sitemap(max_pages: int = 120) -> List[str]:
    index_xml = http_get("https://www.wowhead.com/sitemap")
    sitemap_urls = SITEMAP_LOC_RE.findall(index_xml)
    guide_sitemaps = [u for u in sitemap_urls if "/sitemap/guides" in u]
    guide_sitemaps = guide_sitemaps[:max_pages]

    urls: List[str] = []
    for sm_url in guide_sitemaps:
        try:
            xml = http_get(sm_url)
        except Exception:
            continue
        for loc in SITEMAP_LOC_RE.findall(xml):
            if "/tbc/guide/" in loc.lower():
                urls.append(loc.strip())

    dedup: List[str] = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        dedup.append(u)
    return dedup


def save_html(dest_dir: Path, html: str, fallback_name: str) -> Path:
    title = extract_title(html) or fallback_name
    if not title.lower().endswith("wowhead"):
        title = f"{title} - Wowhead"
    filename = f"{title}.html"
    path = dest_dir / filename
    path.write_text(html, encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Download missing Wowhead BiS guide HTML files based on coverage JSON."
    )
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default=here / "batch_extracted_items.json",
        help="Path to coverage JSON generated by batch_extract_and_report.py",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=here,
        help="Destination directory for downloaded HTML files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of missing guides to attempt in one run",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.2,
        help="Delay in seconds between network requests",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print planned downloads; do not write files.",
    )
    parser.add_argument(
        "--min-slot-count",
        type=int,
        default=3,
        help=(
            "Treat bis_guide_found rows with fewer than this many slots as incomplete "
            "and attempt re-download (default: 3)."
        ),
    )
    parser.add_argument(
        "--exclude-spec",
        action="append",
        default=[],
        help=(
            "Spec name to skip (can be repeated). "
            "Known unsupported specs are skipped by default."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    coverage = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    excluded_specs = set(KNOWN_UNSUPPORTED_SPECS)
    excluded_specs.update(args.exclude_spec)
    missing = missing_phase_rows(coverage, args.min_slot_count, excluded_specs)[: args.limit]

    if not missing:
        print("No missing spec/phase BiS guides found in coverage JSON.")
        return 0

    print(f"Missing BiS rows to attempt: {len(missing)}")
    if excluded_specs:
        print(f"Excluded specs: {', '.join(sorted(excluded_specs))}")
    sitemap_urls = list_tbc_guide_urls_from_sitemap()
    print(f"Indexed TBC guide URLs from sitemap: {len(sitemap_urls)}")

    downloaded = 0
    failed: List[str] = []

    for spec, phase in missing:
        label = f"{spec} {phase}"
        try:
            prefiltered = filter_sitemap_candidates(sitemap_urls, spec)
            pool = prefiltered if prefiltered else sitemap_urls
            candidates = sorted(
                pool,
                key=lambda u: score_candidate(u, spec, phase),
                reverse=True,
            )
            candidates = [u for u in candidates if score_candidate(u, spec, phase) > 0][:20]
            if not candidates:
                candidates = search_wowhead_candidates(spec, phase)
            if not candidates:
                candidates = search_duckduckgo_candidates(spec, phase)
            best = choose_best_candidate(candidates, spec, phase)
            if not best:
                failed.append(f"{label}: no candidate URL")
                continue
            time.sleep(args.delay)
            html = http_get(best)
            page_title = extract_title(html) or ""
            if not looks_like_expected_guide(best, page_title, spec, phase):
                failed.append(f"{label}: candidate mismatch ({best})")
                continue
            if args.dry_run:
                print(f"[dry-run] {label} -> {best}")
                continue

            saved = save_html(args.dest_dir, html, f"{spec} {phase}")
            downloaded += 1
            print(f"[ok] {label} -> {saved.name}")
        except Exception as exc:
            failed.append(f"{label}: {exc}")

    print(f"\nDownloaded: {downloaded}")
    print(f"Failed: {len(failed)}")
    if failed:
        for line in failed:
            print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
