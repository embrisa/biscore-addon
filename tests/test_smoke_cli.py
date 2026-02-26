from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.extract_wowhead_items import extract_by_slot, extract_item_lookup, extract_markup


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_module_help(module: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_help_for_all_modules() -> None:
    modules = [
        "scripts.download_missing_guides",
        "scripts.download_missing_gems_enchants",
        "scripts.extract_wowhead_items",
        "scripts.batch_extract_and_report",
        "scripts.report_batch_items",
    ]
    for module in modules:
        result = _run_module_help(module)
        assert result.returncode == 0, f"{module} failed: {result.stderr}"
        assert "usage" in result.stdout.lower()


def test_extract_markup_sanity() -> None:
    markup = (
        '[h3 toc="Head"]Head[/h3]'
        '[table][tr][td]Rank 1[/td][td][item=12345][/td][td]Source[/td][/tr][/table]'
    )
    item_lookup = {"12345": {"name_enus": "Example Helm"}}
    html = (
        f"<html><head><title>Fixture</title></head><body>"
        f"<script>WH.markup.printHtml({json.dumps(markup)});"
        f"WH.Gatherer.addData(3, 5, {json.dumps(item_lookup)});</script>"
        f"</body></html>"
    )

    extracted_markup = extract_markup(html)
    lookup = extract_item_lookup(html)
    slots = extract_by_slot(extracted_markup, lookup, guide_type="bis")

    assert len(slots) == 1
    assert slots[0]["slot"] == "Head"
    assert slots[0]["items"][0]["item_id"] == 12345
    assert slots[0]["items"][0]["item_name"] == "Example Helm"
