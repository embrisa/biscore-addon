#!/usr/bin/env python3
"""Rename downloaded Wowhead guide files to Windows-safe filenames in place."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import urllib.parse
from typing import Dict, Iterable, List, Tuple


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


def sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


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


def iter_pages(spec: Dict) -> Iterable[Dict]:
    if isinstance(spec.get("downloaded_pages"), list):
        yield from spec["downloaded_pages"]
    if isinstance(spec.get("guides"), list):
        yield from spec["guides"]


def migrate_manifest(manifest: Dict, downloads_root: pathlib.Path, dry_run: bool) -> Tuple[int, int, int]:
    renamed = 0
    updated_paths = 0
    missing = 0

    for spec in manifest.get("specs", []):
        for page in iter_pages(spec):
            url = page.get("url")
            local_path = page.get("local_path")
            if not url or not local_path:
                continue
            old_rel = pathlib.Path(local_path)
            new_rel = old_rel.parent / safe_filename_for_url(url)
            if new_rel != old_rel:
                page["local_path"] = str(new_rel)
                updated_paths += 1
            old_abs = downloads_root / old_rel
            new_abs = downloads_root / new_rel
            if old_abs == new_abs:
                continue
            if not old_abs.exists():
                missing += 1
                continue
            new_abs.parent.mkdir(parents=True, exist_ok=True)
            if new_abs.exists():
                # Keep existing target if content is already there.
                if old_abs.read_bytes() == new_abs.read_bytes():
                    if not dry_run:
                        old_abs.unlink()
                    renamed += 1
                    continue
                raise RuntimeError(f"Target already exists with different content: {new_abs}")
            if not dry_run:
                old_abs.rename(new_abs)
            renamed += 1

    return renamed, updated_paths, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename downloaded guide files to Windows-safe paths.")
    parser.add_argument(
        "--manifest",
        default="downloads/wowhead_tbc_bis/manifest.json",
        help="Path to manifest.json",
    )
    parser.add_argument(
        "--downloads-root",
        default="downloads/wowhead_tbc_bis",
        help="Root directory where downloaded HTML files are stored.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without writing.")
    args = parser.parse_args()

    manifest_path = pathlib.Path(args.manifest).resolve()
    downloads_root = pathlib.Path(args.downloads_root).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    renamed, updated_paths, missing = migrate_manifest(manifest, downloads_root, args.dry_run)
    if not args.dry_run:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"[{mode}] renamed_files={renamed} updated_manifest_paths={updated_paths} missing_sources={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
