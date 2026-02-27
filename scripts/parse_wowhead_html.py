#!/usr/bin/env python3
"""Generate BiScore Lua data tables from downloaded Wowhead TBC guides."""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


CLASS_MAP = {
    "druid": "DRUID",
    "hunter": "HUNTER",
    "mage": "MAGE",
    "paladin": "PALADIN",
    "priest": "PRIEST",
    "rogue": "ROGUE",
    "shaman": "SHAMAN",
    "warlock": "WARLOCK",
    "warrior": "WARRIOR",
}

PROFILE_LABELS = {
    "druid_balance": "Balance",
    "druid_feral_dps": "Feral (Cat)",
    "druid_feral_tank": "Feral (Bear)",
    "druid_restoration": "Restoration",
    "hunter_beast_mastery": "Beast Mastery",
    "hunter_marksmanship": "Marksmanship",
    "hunter_survival": "Survival",
    "mage_arcane": "Arcane",
    "mage_fire": "Fire",
    "mage_frost": "Frost",
    "paladin_holy": "Holy",
    "paladin_protection": "Protection",
    "paladin_retribution": "Retribution",
    "priest_discipline": "Discipline",
    "priest_holy": "Holy",
    "priest_shadow": "Shadow",
    "rogue_assassination": "Assassination",
    "rogue_combat": "Combat",
    "rogue_subtlety": "Subtlety",
    "shaman_elemental": "Elemental",
    "shaman_enhancement": "Enhancement",
    "shaman_restoration": "Restoration",
    "warlock_affliction": "Affliction",
    "warlock_demonology": "Demonology",
    "warlock_destruction": "Destruction",
    "warrior_arms": "Arms",
    "warrior_fury": "Fury",
    "warrior_protection": "Protection",
}

WEIGHT_TOKEN_MAP = {
    "Agility": "ITEM_MOD_AGILITY_SHORT",
    "Strength": "ITEM_MOD_STRENGTH_SHORT",
    "Stamina": "ITEM_MOD_STAMINA_SHORT",
    "Intellect": "ITEM_MOD_INTELLECT_SHORT",
    "Spirit": "ITEM_MOD_SPIRIT_SHORT",
    "HitRating": "ITEM_MOD_HIT_RATING_SHORT",
    "CritRating": "ITEM_MOD_CRIT_RATING_SHORT",
    "HasteRating": "ITEM_MOD_HASTE_RATING_SHORT",
    "ExpertiseRating": "ITEM_MOD_EXPERTISE_RATING_SHORT",
    "DefenseRating": "ITEM_MOD_DEFENSE_SKILL_RATING_SHORT",
    "DodgeRating": "ITEM_MOD_DODGE_RATING_SHORT",
    "BlockRating": "ITEM_MOD_BLOCK_RATING_SHORT",
    "BlockValue": "ITEM_MOD_BLOCK_VALUE_SHORT",
    "Ap": "ITEM_MOD_ATTACK_POWER_SHORT",
    "Rap": "ITEM_MOD_RANGED_ATTACK_POWER_SHORT",
    "FeralAp": "ITEM_MOD_FERAL_ATTACK_POWER_SHORT",
    "SpellDamage": "ITEM_MOD_SPELL_POWER_SHORT",
    "SpellPower": "ITEM_MOD_SPELL_POWER_SHORT",
    "ArcaneSpellDamage": "ITEM_MOD_SPELL_POWER_SHORT",
    "FireSpellDamage": "ITEM_MOD_SPELL_POWER_SHORT",
    "FrostSpellDamage": "ITEM_MOD_SPELL_POWER_SHORT",
    "HolySpellDamage": "ITEM_MOD_SPELL_POWER_SHORT",
    "NatureSpellDamage": "ITEM_MOD_SPELL_POWER_SHORT",
    "ShadowSpellDamage": "ITEM_MOD_SPELL_POWER_SHORT",
    "Healing": "ITEM_MOD_HEALING_DONE_SHORT",
    "SpellHitRating": "ITEM_MOD_SPELL_HIT_RATING_SHORT",
    "SpellCritRating": "ITEM_MOD_SPELL_CRIT_RATING_SHORT",
    "SpellHasteRating": "ITEM_MOD_SPELL_HASTE_RATING_SHORT",
    "Mp5": "ITEM_MOD_MANA_REGENERATION_SHORT",
    "ResilienceRating": "RESILIENCE_RATING",
}

PHASE_CATEGORY = {
    1: "phase_1",
    2: "phase_2",
    3: "phase_3",
    4: "phase_4",
    5: "phase_5",
}


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_noscript(html_text: str) -> Optional[str]:
    match = re.search(r"<noscript>(.*?)</noscript>", html_text, re.S | re.I)
    if not match:
        return None
    return match.group(1)

def unescape_js_string(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\/", "/")
        .replace("\\\\", "\\")
    )

def extract_guide_markup(html_text: str) -> Optional[str]:
    pattern = re.compile(
        r'WH\.markup\.printHtml\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"guide-body"',
        re.S,
    )
    match = pattern.search(html_text)
    if not match:
        return None
    return unescape_js_string(match.group(1))


def section_slot_ids(heading_text: str, section_text: str = "") -> List[int]:
    lowered = heading_text.lower()
    if "head" in lowered:
        return [1]
    if "neck" in lowered:
        return [2]
    if "shoulder" in lowered:
        return [3]
    if "back" in lowered or "cloak" in lowered:
        return [15]
    if "chest" in lowered:
        return [5]
    if "wrist" in lowered:
        return [9]
    has_dual_wield = "dual-wield" in lowered or "dual wield" in lowered
    section_lowered = (section_text or "").lower()
    if (
        "idol" in lowered
        or "relic" in lowered
        or "totem" in lowered
        or "libram" in lowered
        or "ranged" in lowered
        or "wand" in lowered
    ):
        return [18]
    has_offhand = (
        "off-hand" in lowered
        or "off hand" in lowered
        or "offhand" in lowered
        or "offhands" in lowered
        or "shield" in lowered
        or "off-hand" in section_lowered
        or "off hand" in section_lowered
        or "offhand" in section_lowered
        or "offhands" in section_lowered
    )
    has_mainhand = (
        "weapon" in lowered
        or "main hand" in lowered
        or "main-hand" in lowered
        or "mainhand" in lowered
        or "mainhands" in lowered
        or "main hand" in section_lowered
        or "main-hand" in section_lowered
        or "mainhand" in section_lowered
    )
    is_weapon_hand_section = (
        has_dual_wield
        or "weapon" in lowered
        or "handed" in lowered
        or "one-hand" in lowered
        or "one hand" in lowered
        or "1-hand" in lowered
        or "1 hand" in lowered
        or "two-hand" in lowered
        or "two hand" in lowered
        or "2-hand" in lowered
        or "2 hand" in lowered
        or "main hand" in lowered
        or "off-hand" in lowered
        or "off hand" in lowered
        or "mainhand" in lowered
        or "offhand" in lowered
        or "mainhands" in lowered
        or "offhands" in lowered
    )
    if ("hand" in lowered or "glove" in lowered) and not is_weapon_hand_section:
        return [10]
    if "waist" in lowered or "belt" in lowered:
        return [6]
    if "leg" in lowered:
        return [7]
    if "feet" in lowered or "boot" in lowered:
        return [8]
    if "ring" in lowered:
        return [11, 12]
    if "trinket" in lowered:
        return [13, 14]
    if has_dual_wield:
        return [16, 17]
    if has_offhand and has_mainhand:
        return [16, 17]
    if has_offhand:
        return [17]
    if has_mainhand and has_offhand:
        return [16, 17]
    if has_mainhand:
        return [16]
    return []


def parse_ranked_items_from_table(table_html: str) -> List[int]:
    ranked: List[int] = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)
    if not rows:
        rows = re.findall(r"\[tr\](.*?)\[/tr\]", table_html, re.S | re.I)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
        if not cells:
            cells = re.findall(r"\[td[^\]]*\](.*?)\[/td\]", row, re.S | re.I)
        if len(cells) < 2:
            continue
        item_cell = cells[1]
        item_ids = [int(x) for x in re.findall(r"/tbc/item=(\d+)", item_cell, re.I)]
        if not item_ids:
            item_ids = [int(x) for x in re.findall(r"\[item=\s*(\d+)\s*\]", item_cell, re.I)]
        for item_id in item_ids:
            if item_id not in ranked:
                ranked.append(item_id)
    return ranked


def parse_linked_item_ids(section_html: str) -> List[int]:
    ranked: List[int] = []
    item_ids = [int(x) for x in re.findall(r"/tbc/item=(\d+)", section_html, re.I)]
    if not item_ids:
        item_ids = [int(x) for x in re.findall(r"\[item=\s*(\d+)\s*\]", section_html, re.I)]
    for item_id in item_ids:
        if item_id not in ranked:
            ranked.append(item_id)
    return ranked


def parse_guide_slots(guide_path: pathlib.Path) -> Dict[int, List[int]]:
    html_text = guide_path.read_text(encoding="utf-8", errors="replace")
    markup = extract_guide_markup(html_text)
    if markup:
        sections = list(re.finditer(r"\[h[2-6][^\]]*\](.*?)\[/h[2-6]\]", markup, re.S | re.I))
        source_text = markup
    else:
        noscript = extract_noscript(html_text)
        if not noscript:
            return {}
        sections = list(re.finditer(r"<h[2-6][^>]*>(.*?)</h[2-6]>", noscript, re.S | re.I))
        source_text = noscript

    slot_to_items: Dict[int, List[int]] = {}

    for idx, match in enumerate(sections):
        heading = clean_text(match.group(1))
        start = match.end()
        end = sections[idx + 1].start() if idx + 1 < len(sections) else len(source_text)
        section_html = source_text[start:end]
        target_slots = section_slot_ids(heading, section_html)
        if not target_slots:
            continue

        ranked: List[int] = []
        if markup:
            table_blocks = re.findall(r"\[table[^\]]*\](.*?)\[/table\]", section_html, re.S | re.I)
            for table_inner in table_blocks:
                table_markup = f"[table]{table_inner}[/table]"
                parsed = parse_ranked_items_from_table(table_markup)
                for item_id in parsed:
                    if item_id not in ranked:
                        ranked.append(item_id)
                if not parsed:
                    for item_id in [int(x) for x in re.findall(r"\[item=(\d+)\]", table_markup, re.I)]:
                        if item_id not in ranked:
                            ranked.append(item_id)
        else:
            table_blocks = re.findall(r"<table[^>]*>.*?</table>", section_html, re.S | re.I)
            for table_html in table_blocks:
                for item_id in parse_ranked_items_from_table(table_html):
                    if item_id not in ranked:
                        ranked.append(item_id)
        if not ranked:
            ranked = parse_linked_item_ids(section_html)
        if not ranked:
            continue
        for slot_id in target_slots:
            slot_to_items[slot_id] = ranked
    return slot_to_items


def merge_slot_maps(prev_slots: Dict[int, List[int]], curr_slots: Dict[int, List[int]]) -> Dict[int, List[int]]:
    """Keep prior-phase ranked items when entering a new phase."""
    merged: Dict[int, List[int]] = {}
    all_slot_ids = set(prev_slots.keys()) | set(curr_slots.keys())
    for slot_id in all_slot_ids:
        ordered: List[int] = []
        for item_id in curr_slots.get(slot_id, []):
            if item_id not in ordered:
                ordered.append(item_id)
        for item_id in prev_slots.get(slot_id, []):
            if item_id not in ordered:
                ordered.append(item_id)
        if ordered:
            merged[slot_id] = ordered
    return merged


def map_weights(raw_weights: Dict[str, float]) -> Dict[str, float]:
    output: Dict[str, float] = {}
    for key, value in raw_weights.items():
        token = WEIGHT_TOKEN_MAP.get(key)
        if not token:
            continue
        if abs(value) < 1e-9:
            continue
        output[token] = max(output.get(token, 0.0), float(value))
    return output


def build_spec_phase_paths(spec_blob: Dict) -> Dict[int, pathlib.Path]:
    by_category = {
        item.get("category"): item.get("local_path")
        for item in spec_blob.get("downloaded_pages", [])
        if isinstance(item, dict)
    }
    phase_paths: Dict[int, pathlib.Path] = {}
    for phase in range(1, 6):
        category = PHASE_CATEGORY[phase]
        local_path = by_category.get(category)
        if not local_path and phase == 1:
            local_path = by_category.get("phase_pre_raid")
        if local_path:
            phase_paths[phase] = pathlib.Path(local_path)
    return phase_paths


def lua_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_class_file(path: pathlib.Path, class_token: str, profiles: Dict[str, Dict[int, Dict]]) -> None:
    lines: List[str] = []
    lines.append("BiScoreData = BiScoreData or {}")
    lines.append(f'BiScoreData["{class_token}"] = BiScoreData["{class_token}"] or {{')

    for profile_name in sorted(profiles):
        lines.append(f"    [{lua_quote(profile_name)}] = {{")
        for phase in range(1, 6):
            phase_data = profiles[profile_name].get(phase, {"slots": {}, "weights": {}, "scoring": {}})
            lines.append(f"        [{phase}] = {{")
            lines.append("            slots = {")
            for slot_id in sorted(phase_data["slots"]):
                ranked = phase_data["slots"][slot_id]
                items = ", ".join(f"[{i + 1}] = {item_id}" for i, item_id in enumerate(ranked))
                lines.append(f"                [{slot_id}] = {{ ranked = {{ {items} }} }},")
            lines.append("            },")
            lines.append("            weights = {")
            for stat_key in sorted(phase_data["weights"]):
                lines.append(f'                ["{stat_key}"] = {phase_data["weights"][stat_key]:.4f},')
            lines.append("            },")
            lines.append("            scoring = { floor = 0.35, cap = 1.00 },")
            lines.append("        },")
        lines.append("    },")

    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate BiScore class data files from downloaded Wowhead HTML.")
    parser.add_argument("--manifest", default="downloads/wowhead_tbc_bis/manifest.json", help="Path to manifest.json")
    parser.add_argument("--downloads-root", default="downloads/wowhead_tbc_bis", help="Root directory containing downloaded wowhead html files")
    parser.add_argument("--weights", default="state_weights_per_spec.json", help="Path to stat weight json")
    parser.add_argument("--output-dir", default="BiScore/data", help="Directory for generated class lua files")
    args = parser.parse_args()

    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    weights_raw = json.loads(pathlib.Path(args.weights).read_text(encoding="utf-8"))
    downloads_root = pathlib.Path(args.downloads_root)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    per_class_profiles: Dict[str, Dict[str, Dict[int, Dict]]] = defaultdict(lambda: defaultdict(dict))

    specs = manifest.get("specs", [])
    for spec_blob in specs:
        phase_paths = build_spec_phase_paths(spec_blob)
        covered_specs = spec_blob.get("covered_specs", [])

        for spec_key in covered_specs:
            profile_name = PROFILE_LABELS.get(spec_key)
            if not profile_name:
                continue
            class_slug = spec_key.split("_", 1)[0]
            class_token = CLASS_MAP.get(class_slug)
            if not class_token:
                continue

            weights = map_weights(weights_raw.get(spec_key, {}))
            prev_slot_map: Dict[int, List[int]] = {}
            for phase in range(1, 6):
                slot_map: Dict[int, List[int]] = {}
                relative_path = phase_paths.get(phase)
                if relative_path:
                    full_path = downloads_root / relative_path
                    if full_path.exists():
                        slot_map = parse_guide_slots(full_path)

                if phase > 1:
                    slot_map = merge_slot_maps(prev_slot_map, slot_map)

                if slot_map:
                    per_class_profiles[class_token][profile_name][phase] = {
                        "slots": slot_map,
                        "weights": weights,
                    }
                    prev_slot_map = slot_map

    class_files = {
        "DRUID": "druid.lua",
        "HUNTER": "hunter.lua",
        "MAGE": "mage.lua",
        "PALADIN": "paladin.lua",
        "PRIEST": "priest.lua",
        "ROGUE": "rogue.lua",
        "SHAMAN": "shaman.lua",
        "WARLOCK": "warlock.lua",
        "WARRIOR": "warrior.lua",
    }

    for class_token, filename in class_files.items():
        profiles = per_class_profiles.get(class_token, {})
        if not profiles:
            profiles = {}
        write_class_file(output_dir / filename, class_token, profiles)

    print(f"Generated Lua data files in: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
