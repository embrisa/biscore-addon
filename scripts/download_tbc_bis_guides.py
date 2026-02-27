#!/usr/bin/env python3
"""Download WoW TBC BiS, gem, and enchant guides for all specs.

This script starts from the Wowhead TBC BiS index page and:
1) Finds all pre-raid BiS guide URLs (one per spec).
2) Processes each spec sequentially.
3) Discovers phase guide URLs (pre-raid + phase 1-5) and gem/enchant pages.
4) Downloads each guide HTML for offline use.
5) Writes a manifest JSON describing everything fetched.

JavaScript note:
  Wowhead renders a lot of content with JavaScript. Raw HTML downloads do *not*
  populate the visible listview divs—those stay empty. However, the full guide
  body (including every [item=id] and [spell=id]) is embedded in the page inside
  a script tag as the argument to WH.markup.printHtml("..."). So you can get
  all BiS item IDs from the saved HTML without running a browser. Use:
    scripts/extract_wowhead_guide_markup.py <path-to-downloaded-html-or-dir>
  For fully-rendered DOM (e.g. for screenshots or DOM-based parsing), use
  --use-browser (requires: pip install playwright && playwright install chromium).
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import pathlib
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None  # type: ignore[misc, assignment]
    _PLAYWRIGHT_AVAILABLE = False

WOWHEAD_ROOT = "https://www.wowhead.com"
DEFAULT_INDEX_URL = (
    "https://www.wowhead.com/tbc/guides/classes/best-in-slot-guides-burning-crusade-classic"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

GUIDE_URL_PATTERN = re.compile(r"https://www\.wowhead\.com/tbc/guide/[A-Za-z0-9/_\-]+")
PRE_RAID_LINK_PATTERN = re.compile(
    r'href="(/tbc/guide/classes/[^"]*?bis-gear-pve-pre-raid)"'
)

# Fallback: full list of TBC pre-raid BiS guide URLs if index fetch returns incomplete/403.
FALLBACK_PRE_RAID_URLS: List[str] = [
    "https://www.wowhead.com/tbc/guide/classes/druid/balance/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/druid/feral/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/druid/feral/tank-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/druid/healer-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/hunter/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/hunter/marksmanship/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/hunter/survival/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/mage/arcane/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/mage/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/mage/frost/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/paladin/holy/healer-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/paladin/retribution/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/paladin/tank-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/priest/healer-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/priest/shadow/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/rogue/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/shaman/elemental/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/shaman/enhancement/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/shaman/healer-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/warlock/affliction/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/warlock/demonology/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/warlock/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/warrior/dps-bis-gear-pve-pre-raid",
    "https://www.wowhead.com/tbc/guide/classes/warrior/protection/tank-bis-gear-pve-pre-raid",
]
GUIDE_NAV_ID_PATTERN = re.compile(
    r'<script type="application/json" id="(data\.wowhead-guid[^"]+)">(.*?)</script>',
    re.S,
)
GUIDE_MAP_PATTERN = re.compile(
    r'"(\d+)":\{"name":"([^"]+)","category":\d+,"url":"(https://www\.wowhead\.com/tbc/guide/[^"]+)"\}'
)
GUIDE_REF_PATTERN = re.compile(r"\[url guide=(\d+)\]([^\[]+)\[/url\]")

_REQUEST_LOCK = threading.Lock()
_NEXT_REQUEST_AT = 0.0

# Canonical spec IDs requested for offline BiS extraction.
EXPECTED_SPECS: Set[str] = {
    "druid_balance",
    "druid_feral_dps",
    "druid_feral_tank",
    "druid_restoration",
    "hunter_beast_mastery",
    "hunter_marksmanship",
    "hunter_survival",
    "mage_arcane",
    "mage_fire",
    "mage_frost",
    "paladin_holy",
    "paladin_protection",
    "paladin_retribution",
    "priest_discipline",
    "priest_holy",
    "priest_shadow",
    "rogue_subtlety",
    "rogue_combat",
    "rogue_assassination",
    "shaman_elemental",
    "shaman_enhancement",
    "shaman_restoration",
    "warlock_affliction",
    "warlock_demonology",
    "warlock_destruction",
    "warrior_arms",
    "warrior_fury",
    "warrior_protection",
}


@dataclass
class GuideRecord:
    label: str
    guide_id: Optional[str]
    url: str
    local_path: str
    category: str


@dataclass
class SpecResult:
    spec_key: str
    seed_url: str
    layout: str = "single_spec"
    covered_specs: List[str] = field(default_factory=list)
    guides: List[GuideRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def wait_for_request_slot(min_delay: float, max_delay: float) -> None:
    global _NEXT_REQUEST_AT

    # Global pacing across all worker threads to avoid bursty traffic.
    delay = random.uniform(min_delay, max_delay)
    with _REQUEST_LOCK:
        now = time.monotonic()
        if now < _NEXT_REQUEST_AT:
            time.sleep(_NEXT_REQUEST_AT - now)
            now = time.monotonic()
        _NEXT_REQUEST_AT = now + delay


def fetch_url(
    url: str,
    retries: int = 5,
    timeout: int = 30,
    min_delay: float = 1.0,
    max_delay: float = 2.5,
) -> str:
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        wait_for_request_slot(min_delay=min_delay, max_delay=max_delay)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://www.wowhead.com/",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as exc:
            last_exc = exc
            # Treat 403/429 as rate limiting and back off longer.
            if exc.code in {403, 429} and attempt < retries:
                time.sleep(8.0 * attempt)
                continue
            if attempt < retries:
                time.sleep(2.0 * attempt)
            else:
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(2.0 * attempt)
            else:
                break
    raise RuntimeError(f"Failed to fetch {url}: {last_exc}")


def fetch_via_browser(
    url: str,
    page: Any,
    wait_after_load_ms: int = 3000,
    min_delay: float = 1.0,
    max_delay: float = 2.5,
) -> str:
    """Fetch URL using a Playwright page (full JS render); return HTML."""
    wait_for_request_slot(min_delay=min_delay, max_delay=max_delay)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(wait_after_load_ms)
    return page.content()


def sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


WINDOWS_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
}


def sanitize_filename_component(value: str) -> str:
    cleaned = WINDOWS_INVALID_FILENAME_CHARS.sub("_", value)
    cleaned = cleaned.strip().strip(".")
    if not cleaned:
        return "unknown"
    if cleaned.lower() in WINDOWS_RESERVED_NAMES:
        return f"_{cleaned}"
    return cleaned


def safe_filename_for_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    if not path_parts:
        name = "index"
    else:
        name = "__".join(sanitize_filename_component(p) for p in path_parts)
    if parsed.query:
        name += "__q_" + sanitize_slug(parsed.query)
    return f"{name}.html"


def extract_pre_raid_urls(index_html: str) -> List[str]:
    urls = {
        urllib.parse.urljoin(WOWHEAD_ROOT, m.group(1))
        for m in PRE_RAID_LINK_PATTERN.finditer(index_html)
    }
    return sorted(urls)


def extract_guide_map(page_html: str) -> Dict[str, Tuple[str, str]]:
    text = page_html.replace("\\/", "/")
    out: Dict[str, Tuple[str, str]] = {}
    for guide_id, name, url in GUIDE_MAP_PATTERN.findall(text):
        out[guide_id] = (name, url)
    return out


def extract_nav_blob(page_html: str) -> Optional[str]:
    m = GUIDE_NAV_ID_PATTERN.search(page_html)
    if not m:
        return None
    encoded = m.group(2)
    try:
        return json.loads(encoded)
    except json.JSONDecodeError:
        return None


def classify_nav_entry(label: str) -> Optional[str]:
    lowered = label.lower()
    if "pre-raid" in lowered and "bis" in lowered:
        return "phase_pre_raid"
    if "phase 1" in lowered and "bis" in lowered:
        return "phase_1"
    if "phase 2" in lowered and "bis" in lowered:
        return "phase_2"
    if "phase 3" in lowered and "bis" in lowered:
        return "phase_3"
    if "phase 4" in lowered and "bis" in lowered:
        return "phase_4"
    if "phase 5" in lowered and "bis" in lowered:
        return "phase_5"
    if ("enchant" in lowered and "gem" in lowered) or "gems & enchants" in lowered:
        return "enchants_gems"
    return None


def parse_role_from_seed_url(seed_url: str) -> Optional[str]:
    parsed = urllib.parse.urlparse(seed_url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None
    leaf = parts[-1]
    # Common examples: dps-bis-gear-pve-pre-raid, tank-bis-gear-pve-pre-raid
    m = re.match(r"([a-z]+)-bis-gear", leaf)
    if not m:
        return None
    role = m.group(1)
    if role in {"dps", "tank", "healer"}:
        return role
    return None


def parse_class_and_spec_from_seed_url(seed_url: str) -> Tuple[Optional[str], Optional[str]]:
    parsed = urllib.parse.urlparse(seed_url)
    parts = [p for p in parsed.path.split("/") if p]
    # Typical shapes:
    #   /tbc/guide/classes/<class>/<spec>/<leaf>
    #   /tbc/guide/classes/<class>/<role>-bis-gear-...   (shared role pages)
    if len(parts) >= 6 and parts[2] == "classes":
        return parts[3], parts[4]
    if len(parts) >= 5 and parts[2] == "classes":
        class_name = parts[3]
        m = re.match(r"^(dps|tank|healer)-", parts[4])
        if m:
            return class_name, m.group(1)
        return class_name, parts[4]
    return None, None


def discover_spec_key(seed_url: str, seed_html: str) -> str:
    url_class, url_spec = parse_class_and_spec_from_seed_url(seed_url)
    if url_class and url_spec:
        class_name = sanitize_slug(url_class)
        spec_name = sanitize_slug(url_spec)
        if spec_name in {"dps", "tank", "healer"}:
            return f"{class_name}-{spec_name}-shared"

    class_match = re.search(r'data-class="([^"]+)"', seed_html)
    spec_match = re.search(r'data-spec="([^"]+)"', seed_html)
    if class_match and spec_match:
        class_name = sanitize_slug(class_match.group(1))
        spec_name = sanitize_slug(spec_match.group(1))
        role = parse_role_from_seed_url(seed_url)
        if role and spec_name == "feral":
            # Feral has both DPS and Tank guides in TBC.
            return f"{class_name}-{spec_name}-{role}"
        if role and spec_name in {"holy", "restoration"}:
            # Healer pages are often role-specific and can collide in slugs.
            return f"{class_name}-{spec_name}-{role}"
        return f"{class_name}-{spec_name}"

    parsed = urllib.parse.urlparse(seed_url)
    return sanitize_slug(parsed.path)


def infer_layout_and_coverage(seed_url: str, seed_html: str, spec_key: str) -> Tuple[str, List[str]]:
    url_class, url_spec = parse_class_and_spec_from_seed_url(seed_url)
    class_name = sanitize_slug(url_class) if url_class else None
    spec_name = sanitize_slug(url_spec) if url_spec else None

    if not class_name or not spec_name:
        class_match = re.search(r'data-class="([^"]+)"', seed_html)
        spec_match = re.search(r'data-spec="([^"]+)"', seed_html)
        if class_match:
            class_name = sanitize_slug(class_match.group(1))
        if spec_match:
            spec_name = sanitize_slug(spec_match.group(1))

    if class_name == "hunter" and spec_name == "dps":
        return (
            "shared_role_guide",
            ["hunter_beast_mastery", "hunter_marksmanship", "hunter_survival"],
        )

    if class_name == "rogue" and spec_name == "dps":
        return (
            "shared_role_guide",
            ["rogue_assassination", "rogue_combat", "rogue_subtlety"],
        )

    if class_name == "warrior" and spec_name == "dps":
        return ("shared_role_guide", ["warrior_arms", "warrior_fury"])

    if class_name == "priest" and spec_name == "healer":
        return ("shared_role_guide", ["priest_discipline", "priest_holy"])

    if class_name == "mage" and spec_name == "dps":
        return ("shared_role_guide", ["mage_fire"])

    if class_name == "warlock" and spec_name == "dps":
        return ("shared_role_guide", ["warlock_destruction"])

    if class_name == "paladin" and spec_name == "tank":
        return ("shared_role_guide", ["paladin_protection"])

    if class_name == "shaman" and spec_name == "healer":
        return ("shared_role_guide", ["shaman_restoration"])

    if class_name == "druid" and spec_name == "healer":
        return ("shared_role_guide", ["druid_restoration"])

    if class_name == "druid" and spec_name == "balance":
        return ("single_spec", ["druid_balance"])
    if class_name == "druid" and spec_name == "feral":
        role = parse_role_from_seed_url(seed_url)
        if role == "tank":
            return ("single_spec", ["druid_feral_tank"])
        return ("single_spec", ["druid_feral_dps"])
    if class_name == "mage" and spec_name == "arcane":
        return ("single_spec", ["mage_arcane"])
    if class_name == "mage" and spec_name == "frost":
        return ("single_spec", ["mage_frost"])
    if class_name == "paladin" and spec_name == "holy":
        return ("single_spec", ["paladin_holy"])
    if class_name == "paladin" and spec_name == "retribution":
        return ("single_spec", ["paladin_retribution"])
    if class_name == "priest" and spec_name == "shadow":
        return ("single_spec", ["priest_shadow"])
    if class_name == "shaman" and spec_name == "elemental":
        return ("single_spec", ["shaman_elemental"])
    if class_name == "shaman" and spec_name == "enhancement":
        return ("single_spec", ["shaman_enhancement"])
    if class_name == "warlock" and spec_name == "affliction":
        return ("single_spec", ["warlock_affliction"])
    if class_name == "warlock" and spec_name == "demonology":
        return ("single_spec", ["warlock_demonology"])
    if class_name == "warrior" and spec_name == "protection":
        return ("single_spec", ["warrior_protection"])

    if class_name and spec_name:
        return ("single_spec", [f"{class_name}_{spec_name}"])

    return ("single_spec", [spec_key.replace("-", "_")])


def write_file(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def unique_records(records: Iterable[GuideRecord]) -> List[GuideRecord]:
    seen: Set[str] = set()
    out: List[GuideRecord] = []
    for rec in records:
        if rec.url in seen:
            continue
        seen.add(rec.url)
        out.append(rec)
    return out


def process_spec(
    seed_url: str,
    output_root: pathlib.Path,
    min_delay: float,
    max_delay: float,
    browser_page: Optional[Any] = None,
    browser_wait_ms: int = 3000,
) -> SpecResult:
    if browser_page is not None:
        seed_html = fetch_via_browser(
            seed_url, browser_page, wait_after_load_ms=browser_wait_ms,
            min_delay=min_delay, max_delay=max_delay,
        )
    else:
        seed_html = fetch_url(seed_url, min_delay=min_delay, max_delay=max_delay)
    spec_key = discover_spec_key(seed_url, seed_html)
    result = SpecResult(spec_key=spec_key, seed_url=seed_url)
    layout, covered_specs = infer_layout_and_coverage(seed_url, seed_html, spec_key)
    result.layout = layout
    result.covered_specs = covered_specs
    guide_map = extract_guide_map(seed_html)
    nav_blob = extract_nav_blob(seed_html)

    if not nav_blob:
        result.warnings.append("Missing navigation blob; only seed page downloaded")

    planned: List[GuideRecord] = []
    planned.append(
        GuideRecord(
            label="Pre-Raid BiS",
            guide_id=None,
            url=seed_url,
            local_path=str(pathlib.Path(spec_key) / safe_filename_for_url(seed_url)),
            category="phase_pre_raid",
        )
    )

    if nav_blob:
        for guide_id, label in GUIDE_REF_PATTERN.findall(nav_blob):
            category = classify_nav_entry(label)
            if not category:
                continue
            mapped = guide_map.get(guide_id)
            if not mapped:
                result.warnings.append(f"Guide id {guide_id} found in nav but not guide map")
                continue
            _, guide_url = mapped
            planned.append(
                GuideRecord(
                    label=label.strip(),
                    guide_id=guide_id,
                    url=guide_url,
                    local_path=str(pathlib.Path(spec_key) / safe_filename_for_url(guide_url)),
                    category=category,
                )
            )

    # Fallback discovery from escaped URLs, in case a phase page is missing in nav parse.
    seed_text = seed_html.replace("\\/", "/")
    for url in GUIDE_URL_PATTERN.findall(seed_text):
        normalized = url.strip()
        if normalized in {p.url for p in planned}:
            continue
        lowered = normalized.lower()
        if "best-in-slot" in lowered or "bis-gear" in lowered:
            # Include known phase-ish variants we can identify from the URL itself.
            cat = None
            if "pre-raid" in lowered:
                cat = "phase_pre_raid"
            elif "phase-2" in lowered:
                cat = "phase_2"
            elif "phase-3" in lowered:
                cat = "phase_3"
            elif "phase-4" in lowered:
                cat = "phase_4"
            elif "phase-5" in lowered:
                cat = "phase_5"
            elif "karazhan" in lowered or "phase-1" in lowered:
                cat = "phase_1"
            if cat:
                planned.append(
                    GuideRecord(
                        label=f"Discovered {cat}",
                        guide_id=None,
                        url=normalized,
                        local_path=str(
                            pathlib.Path(spec_key) / safe_filename_for_url(normalized)
                        ),
                        category=cat,
                    )
                )

    planned = unique_records(planned)

    for rec in planned:
        try:
            if rec.url == seed_url:
                page_html = seed_html
            elif browser_page is not None:
                page_html = fetch_via_browser(
                    rec.url, browser_page, wait_after_load_ms=browser_wait_ms,
                    min_delay=min_delay, max_delay=max_delay,
                )
            else:
                page_html = fetch_url(rec.url, min_delay=min_delay, max_delay=max_delay)
            full_local_path = output_root / rec.local_path
            write_file(full_local_path, page_html)
            result.guides.append(rec)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Failed to download {rec.url}: {exc}")

    # Fetch gem/enchant referenced pages from all downloaded guides for richer offline context.
    extra_links: Set[str] = set()
    for rec in list(result.guides):
        full_path = output_root / rec.local_path
        page_html = full_path.read_text(encoding="utf-8")
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', page_html)
        is_enchants_page = rec.category == "enchants_gems"
        for raw_href in hrefs:
            href = html_lib.unescape(raw_href).replace("\\/", "/")
            lowered = href.lower()
            absolute = urllib.parse.urljoin(WOWHEAD_ROOT, href)
            if not absolute.startswith(WOWHEAD_ROOT + "/tbc/"):
                continue
            # Enchants/Gems pages mostly link directly to item/spell/skill URLs,
            # which often do not contain "gem" or "enchant" in the URL itself.
            if is_enchants_page:
                if not re.search(r"/tbc/(item=|spell=|skill=|guide/)", absolute):
                    continue
            else:
                if "gem" not in lowered and "enchant" not in lowered:
                    continue
            extra_links.add(absolute)

    for url in sorted(extra_links):
        if any(g.url == url for g in result.guides):
            continue
        try:
            if browser_page is not None:
                html = fetch_via_browser(
                    url, browser_page, wait_after_load_ms=browser_wait_ms,
                    min_delay=min_delay, max_delay=max_delay,
                )
            else:
                html = fetch_url(url, min_delay=min_delay, max_delay=max_delay)
            rec = GuideRecord(
                label="Referenced Gem/Enchant Page",
                guide_id=None,
                url=url,
                local_path=str(pathlib.Path(spec_key) / safe_filename_for_url(url)),
                category="gem_enchant_reference",
            )
            write_file(output_root / rec.local_path, html)
            result.guides.append(rec)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Failed to download referenced page {url}: {exc}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download all WoW TBC spec BiS guides + gem/enchant pages."
    )
    parser.add_argument(
        "--index-url",
        default=DEFAULT_INDEX_URL,
        help="Wowhead index page containing pre-raid BiS guide links (ignored if --index-file is set).",
    )
    parser.add_argument(
        "--index-file",
        type=pathlib.Path,
        default=None,
        metavar="PATH",
        help="Read index HTML from a local file instead of fetching. Use this if the index URL returns 403 or you already have index.html (e.g. from a previous run). All 24 pre-raid guide URLs will be taken from this file.",
    )
    parser.add_argument(
        "--output-dir",
        default="downloads/wowhead_tbc_bis",
        help="Directory to write HTML files and manifest.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=1.0,
        help="Minimum seconds between any two outbound requests (global).",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=2.5,
        help="Maximum seconds between any two outbound requests (global jitter).",
    )
    parser.add_argument(
        "--use-browser",
        action="store_true",
        help="Use Playwright/Chromium to load each page (full JS render). Requires: pip install playwright && playwright install chromium. Runs sequentially.",
    )
    parser.add_argument(
        "--browser-wait-ms",
        type=int,
        default=3000,
        help="Milliseconds to wait after page load when using --use-browser.",
    )
    args = parser.parse_args()
    if args.min_delay < 0 or args.max_delay < 0:
        raise ValueError("--min-delay and --max-delay must be >= 0")
    if args.min_delay > args.max_delay:
        raise ValueError("--min-delay cannot be greater than --max-delay")

    if args.use_browser and not _PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("--use-browser requires playwright. Install with: pip install playwright && playwright install chromium")

    output_dir = pathlib.Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    browser_page: Optional[Any] = None
    playwright_context: Any = None
    if args.use_browser:
        playwright_context = sync_playwright().start()
        browser = playwright_context.chromium.launch(headless=True)
        browser_page = browser.new_page()
        print("[0/4] Using Playwright (Chromium) for full JS-rendered HTML")

    if args.index_file is not None:
        index_path = args.index_file.resolve()
        if not index_path.is_file():
            raise FileNotFoundError(f"Index file not found: {index_path}")
        print(f"[1/4] Reading index from file: {index_path}")
        index_html = index_path.read_text(encoding="utf-8", errors="replace")
    else:
        print(f"[1/4] Fetching index: {args.index_url}")
        if browser_page is not None:
            index_html = fetch_via_browser(
                args.index_url, browser_page,
                wait_after_load_ms=args.browser_wait_ms,
                min_delay=args.min_delay, max_delay=args.max_delay,
            )
        else:
            index_html = fetch_url(
                args.index_url, min_delay=args.min_delay, max_delay=args.max_delay
            )
    pre_raid_urls = extract_pre_raid_urls(index_html)
    if len(pre_raid_urls) < 20:
        # Index may be 403/minimal; use hardcoded list so we still process all specs.
        pre_raid_urls = sorted(set(pre_raid_urls) | set(FALLBACK_PRE_RAID_URLS))
        print(f"Index had few links; using fallback list ({len(FALLBACK_PRE_RAID_URLS)} pre-raid URLs)")
    if not pre_raid_urls:
        raise RuntimeError(
            "No pre-raid guide URLs found. "
            "If using --index-file, ensure the file is the full Wowhead BiS index HTML."
        )
    print(f"Found {len(pre_raid_urls)} specialization seed guides")

    print("[2/4] Saving index page")
    write_file(output_dir / "index.html", index_html)

    print("[3/4] Processing specs sequentially")
    results: List[SpecResult] = []
    for seed_url in pre_raid_urls:
        try:
            if browser_page is not None:
                res = process_spec(
                    seed_url, output_dir, args.min_delay, args.max_delay,
                    browser_page=browser_page,
                    browser_wait_ms=args.browser_wait_ms,
                )
            else:
                res = process_spec(
                    seed_url, output_dir, args.min_delay, args.max_delay,
                )
            results.append(res)
            print(
                f"  - {res.spec_key}: downloaded {len(res.guides)} pages"
                + (f", warnings={len(res.warnings)}" if res.warnings else "")
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  - FAILED {seed_url}: {exc}")
    if browser_page is not None and playwright_context is not None:
        try:
            browser_page.close()
        except Exception:  # noqa: S110
            pass
        try:
            browser_page.context.browser.close()
        except Exception:  # noqa: S110
            pass
        playwright_context.stop()

    print("[4/4] Writing manifest")
    covered_specs: Set[str] = set()
    for r in results:
        covered_specs.update(r.covered_specs)
    missing_specs = sorted(EXPECTED_SPECS - covered_specs)
    extra_specs = sorted(covered_specs - EXPECTED_SPECS)

    manifest = {
        "generated_at_epoch": int(time.time()),
        "index_url": args.index_url,
        "spec_count": len(results),
        "expected_specs": sorted(EXPECTED_SPECS),
        "covered_specs": sorted(covered_specs),
        "missing_specs": missing_specs,
        "extra_specs": extra_specs,
        "specs": [
            {
                "spec_key": r.spec_key,
                "seed_url": r.seed_url,
                "layout": r.layout,
                "covered_specs": r.covered_specs,
                "downloaded_pages": [
                    {
                        "label": g.label,
                        "guide_id": g.guide_id,
                        "category": g.category,
                        "url": g.url,
                        "local_path": g.local_path,
                    }
                    for g in sorted(r.guides, key=lambda x: (x.category, x.url))
                ],
                "warnings": r.warnings,
            }
            for r in sorted(results, key=lambda x: x.spec_key)
        ],
    }
    write_file(output_dir / "manifest.json", json.dumps(manifest, indent=2))

    total_files = sum(len(r.guides) for r in results) + 2  # +index +manifest
    print(f"Done. Wrote {total_files} files to: {output_dir}")
    if missing_specs:
        print(f"Coverage warning: missing {len(missing_specs)} specs: {', '.join(missing_specs)}")
    else:
        print("Coverage check: all expected specs represented")
    if extra_specs:
        print(f"Coverage note: found {len(extra_specs)} unexpected specs: {', '.join(extra_specs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
