#!/usr/bin/env python3
"""Download Classic Armory profiles and compute BiScore totals with slot breakdowns."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from parse_wowhead_html import PROFILE_LABELS

try:
    from lupa import LuaRuntime
except ModuleNotFoundError:
    LuaRuntime = None  # type: ignore[assignment]

SCORE_SLOTS = [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]

SLOT_TYPE_TO_ID = {
    "HEAD": 1,
    "NECK": 2,
    "SHOULDER": 3,
    "CHEST": 5,
    "WAIST": 6,
    "LEGS": 7,
    "FEET": 8,
    "WRIST": 9,
    "HANDS": 10,
    "FINGER_1": 11,
    "FINGER_2": 12,
    "TRINKET_1": 13,
    "TRINKET_2": 14,
    "BACK": 15,
    "MAIN_HAND": 16,
    "OFF_HAND": 17,
    "RANGED": 18,
}

SLOT_LABELS = {
    1: "Head",
    2: "Neck",
    3: "Shoulder",
    5: "Chest",
    6: "Waist",
    7: "Legs",
    8: "Feet",
    9: "Wrist",
    10: "Hands",
    11: "Finger 1",
    12: "Finger 2",
    13: "Trinket 1",
    14: "Trinket 2",
    15: "Back",
    16: "Main Hand",
    17: "Off Hand",
    18: "Ranged/Relic",
}

PHASE_TARGET = {1: 1800, 2: 2600, 3: 3200, 4: 3800, 5: 4400}

STAT_FIELD_MAP = {
    "str": "ITEM_MOD_STRENGTH_SHORT",
    "agi": "ITEM_MOD_AGILITY_SHORT",
    "sta": "ITEM_MOD_STAMINA_SHORT",
    "int": "ITEM_MOD_INTELLECT_SHORT",
    "spi": "ITEM_MOD_SPIRIT_SHORT",
    "spr": "ITEM_MOD_SPIRIT_SHORT",
    "hitrtng": "ITEM_MOD_HIT_RATING_SHORT",
    "critstrkrtng": "ITEM_MOD_CRIT_RATING_SHORT",
    "hastertng": "ITEM_MOD_HASTE_RATING_SHORT",
    "exprtng": "ITEM_MOD_EXPERTISE_RATING_SHORT",
    "dodgertng": "ITEM_MOD_DODGE_RATING_SHORT",
    "defrtng": "ITEM_MOD_DEFENSE_SKILL_RATING_SHORT",
    "blockrtng": "ITEM_MOD_BLOCK_RATING_SHORT",
    "blockvalue": "ITEM_MOD_BLOCK_VALUE_SHORT",
    "atkpwr": "ITEM_MOD_ATTACK_POWER_SHORT",
    "rgdatkpwr": "ITEM_MOD_RANGED_ATTACK_POWER_SHORT",
    "feratkpwr": "ITEM_MOD_FERAL_ATTACK_POWER_SHORT",
    "spldmg": "ITEM_MOD_SPELL_POWER_SHORT",
    "splheal": "ITEM_MOD_HEALING_DONE_SHORT",
    "splhitrtng": "ITEM_MOD_SPELL_HIT_RATING_SHORT",
    "splcritstrkrtng": "ITEM_MOD_SPELL_CRIT_RATING_SHORT",
    "splhastertng": "ITEM_MOD_SPELL_HASTE_RATING_SHORT",
    "manargn": "ITEM_MOD_MANA_REGENERATION_SHORT",
    "resirtng": "RESILIENCE_RATING",
}

API_STAT_TYPE_MAP = {
    "STRENGTH": "ITEM_MOD_STRENGTH_SHORT",
    "AGILITY": "ITEM_MOD_AGILITY_SHORT",
    "STAMINA": "ITEM_MOD_STAMINA_SHORT",
    "INTELLECT": "ITEM_MOD_INTELLECT_SHORT",
    "SPIRIT": "ITEM_MOD_SPIRIT_SHORT",
    "HIT_RATING": "ITEM_MOD_HIT_RATING_SHORT",
    "CRIT_RATING": "ITEM_MOD_CRIT_RATING_SHORT",
    "HASTE_RATING": "ITEM_MOD_HASTE_RATING_SHORT",
    "EXPERTISE_RATING": "ITEM_MOD_EXPERTISE_RATING_SHORT",
    "DODGE_RATING": "ITEM_MOD_DODGE_RATING_SHORT",
    "DEFENSE_SKILL_RATING": "ITEM_MOD_DEFENSE_SKILL_RATING_SHORT",
    "BLOCK_RATING": "ITEM_MOD_BLOCK_RATING_SHORT",
    "BLOCK_VALUE": "ITEM_MOD_BLOCK_VALUE_SHORT",
    "ATTACK_POWER": "ITEM_MOD_ATTACK_POWER_SHORT",
    "RANGED_ATTACK_POWER": "ITEM_MOD_RANGED_ATTACK_POWER_SHORT",
    "FERAL_ATTACK_POWER": "ITEM_MOD_FERAL_ATTACK_POWER_SHORT",
    "RESILIENCE_RATING": "RESILIENCE_RATING",
    "HIT_SPELL_RATING": "ITEM_MOD_SPELL_HIT_RATING_SHORT",
    "CRIT_SPELL_RATING": "ITEM_MOD_SPELL_CRIT_RATING_SHORT",
    "HASTE_SPELL_RATING": "ITEM_MOD_SPELL_HASTE_RATING_SHORT",
    "MANA_REGENERATION": "ITEM_MOD_MANA_REGENERATION_SHORT",
}

SPELL_POWER_RE = re.compile(
    r"increases (?:damage and healing done by magical spells and effects|healing done by spells and effects and damage done by spells and effects) by up to (\d+)",
    re.I,
)
HEAL_RE = re.compile(r"increases healing done by up to (\d+)", re.I)
SPELL_DMG_RE = re.compile(r"damage done by up to (\d+)", re.I)
AP_RE = re.compile(r"increases attack power by (\d+)", re.I)
RAP_RE = re.compile(r"increases ranged attack power by (\d+)", re.I)
FERAL_AP_RE = re.compile(r"increases attack power in cat, bear, and dire bear forms only by (\d+)", re.I)
MP5_RE = re.compile(r"restores (\d+) mana per 5 sec", re.I)

CLASS_TOKEN_FROM_NAME = {
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

CLASS_FILE_MAP = {
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

INVENTORY_TYPE_TO_EQUIP_LOC = {
    "TWOHWEAPON": "INVTYPE_2HWEAPON",
    "2HWEAPON": "INVTYPE_2HWEAPON",
}

DEFAULT_CHARACTERS = [
    (
        "https://classic-armory.org/character/eu/tbc-anniversary/thunderstrike/Neaviia",
        "Protection",
    ),
    ("https://classic-armory.org/character/eu/tbc-anniversary/spineshatter/Toya", "Enhancement"),
    (
        "https://classic-armory.org/character/eu/tbc-anniversary/spineshatter/Verstappen",
        "Beast Mastery",
    ),
    (
        "https://classic-armory.org/character/eu/tbc-anniversary/spineshatter/CasualGurra",
        "Retribution",
    ),
    ("https://classic-armory.org/character/eu/tbc-anniversary/spineshatter/Zipere", "Enhancement"),
]


@dataclass
class CharacterQuery:
    url: str
    region: str
    flavor: str
    realm: str
    name: str
    profile: str


class HttpClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": "BiScoreAddon/1.0 (+https://classic-armory.org)",
            "Accept": "application/json, text/plain, */*",
        }

    def get_text(self, url: str) -> str:
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))


class WowheadCache:
    def __init__(self, client: HttpClient) -> None:
        self.client = client
        self.stats_cache: Dict[int, Dict[str, float]] = {}
        self.equip_cache: Dict[int, Dict[str, Any]] = {}

    def get_equip(self, item_id: int) -> Dict[str, Any]:
        if item_id in self.equip_cache:
            return self.equip_cache[item_id]

        url = f"https://www.wowhead.com/tbc/item={item_id}?xml"
        equip: Dict[str, Any] = {}
        try:
            xml_text = self.client.get_text(url)
            root = ET.fromstring(xml_text)
            node = root.find("./item/jsonEquip")
            if node is not None and node.text:
                payload = "{" + node.text.strip() + "}"
                equip = json.loads(payload)
        except Exception:
            equip = {}

        self.equip_cache[item_id] = equip
        return equip

    def get_stats(self, item_id: int) -> Dict[str, float]:
        if item_id in self.stats_cache:
            return self.stats_cache[item_id]

        stats: Dict[str, float] = {}
        equip = self.get_equip(item_id)
        for key, value in equip.items():
            token = STAT_FIELD_MAP.get(key)
            if not token:
                continue
            if isinstance(value, (int, float)):
                stats[token] = stats.get(token, 0.0) + float(value)

        self.stats_cache[item_id] = stats
        return stats

    def get_socket_count(self, item_id: int) -> int:
        equip = self.get_equip(item_id)
        value = equip.get("nsockets")
        if isinstance(value, (int, float)):
            return max(0, int(value))
        return 0


class LuaScorer:
    def __init__(self, core_dir: pathlib.Path, data_dir: pathlib.Path) -> None:
        if LuaRuntime is None:
            raise RuntimeError("Missing dependency 'lupa'. Install with: python3 -m pip install --user lupa")
        self.core_dir = core_dir
        self.data_dir = data_dir
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self._init_runtime()

    def _exec_file(self, path: pathlib.Path) -> None:
        self.lua.execute(path.read_text(encoding="utf-8"))

    def _to_lua(self, value: Any) -> Any:
        if isinstance(value, dict):
            table = self.lua.table()
            for k, v in value.items():
                table[k] = self._to_lua(v)
            return table
        if isinstance(value, list):
            table = self.lua.table()
            for idx, v in enumerate(value, start=1):
                table[idx] = self._to_lua(v)
            return table
        return value

    def _from_lua(self, value: Any) -> Any:
        if hasattr(value, "items"):
            out: Dict[Any, Any] = {}
            for k, v in value.items():
                out[k] = self._from_lua(v)
            return out
        return value

    def _init_runtime(self) -> None:
        self.lua.execute(
            """
            BiScore = BiScore or {}
            BiScoreData = BiScoreData or {}
            BiScoreDB = BiScoreDB or {}
            BiScoreCharDB = BiScoreCharDB or {}

            local armory = {
              classToken = nil,
              itemLinksBySlot = {},
              itemStatsByLink = {},
              equipLocByLink = {},
            }

            function SetArmoryRuntime(classToken, itemLinksBySlot, itemStatsByLink, equipLocByLink)
              armory.classToken = classToken
              armory.itemLinksBySlot = itemLinksBySlot or {}
              armory.itemStatsByLink = itemStatsByLink or {}
              armory.equipLocByLink = equipLocByLink or {}
            end

            function UnitExists(unit)
              return unit == "armory"
            end

            function UnitClass(unit)
              if unit ~= "armory" then
                return nil, nil
              end
              return armory.classToken, armory.classToken
            end

            function GetInventoryItemLink(unit, slotID)
              if unit ~= "armory" then
                return nil
              end
              return armory.itemLinksBySlot[slotID]
            end

            function GetItemStats(itemLink)
              return armory.itemStatsByLink[itemLink]
            end

            function GetItemInfo(itemLink)
              local equipLoc = armory.equipLocByLink[itemLink]
              return nil, nil, nil, nil, nil, nil, nil, nil, equipLoc
            end
            """
        )
        self._exec_file(self.core_dir / "phase.lua")
        self._exec_file(self.core_dir / "scoring.lua")
        for class_file in CLASS_FILE_MAP.values():
            self._exec_file(self.data_dir / class_file)

    def score_character(
        self,
        class_token: str,
        profile_name: str,
        phase: int,
        item_links_by_slot: Dict[int, str],
        item_stats_by_link: Dict[str, Dict[str, float]],
        equip_loc_by_link: Dict[str, str],
    ) -> Dict[str, Any]:
        self.lua.globals().SetArmoryRuntime(
            class_token,
            self._to_lua(item_links_by_slot),
            self._to_lua(item_stats_by_link),
            self._to_lua(equip_loc_by_link),
        )
        addon = self.lua.globals().BiScore
        self.lua.globals().BiScoreCharDB["phase"] = int(phase)
        addon.InitPhase(addon)
        addon.InitScoring(addon)
        result = addon.GetUnitBiScore(addon, "armory", profile_name)
        if result is None:
            raise ValueError(
                f"Lua scoring returned nil for class={class_token}, profile={profile_name}, phase={phase}"
            )
        return self._from_lua(result)


def parse_character_url(url: str) -> Tuple[str, str, str, str]:
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 5 or parts[0] != "character":
        raise ValueError(f"Unsupported character URL: {url}")
    return parts[1], parts[2], parts[3], parts[4]


def parse_character_arg(value: str) -> Tuple[str, str]:
    if "|" not in value:
        raise ValueError("Use --character '<url>|<profile>'")
    url, profile = value.split("|", 1)
    return url.strip(), profile.strip()


def extract_spell_stat_hints(equipment_item: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for spell in equipment_item.get("spells", []) or []:
        desc = (spell.get("description") or "").strip()
        if not desc:
            continue
        m = SPELL_POWER_RE.search(desc)
        if m:
            out["ITEM_MOD_SPELL_POWER_SHORT"] = out.get("ITEM_MOD_SPELL_POWER_SHORT", 0.0) + float(m.group(1))
        m = HEAL_RE.search(desc)
        if m:
            out["ITEM_MOD_HEALING_DONE_SHORT"] = out.get("ITEM_MOD_HEALING_DONE_SHORT", 0.0) + float(m.group(1))
        m = SPELL_DMG_RE.search(desc)
        if m and "ITEM_MOD_SPELL_POWER_SHORT" not in out:
            out["ITEM_MOD_SPELL_POWER_SHORT"] = out.get("ITEM_MOD_SPELL_POWER_SHORT", 0.0) + float(m.group(1))
        m = AP_RE.search(desc)
        if m:
            out["ITEM_MOD_ATTACK_POWER_SHORT"] = out.get("ITEM_MOD_ATTACK_POWER_SHORT", 0.0) + float(m.group(1))
        m = RAP_RE.search(desc)
        if m:
            out["ITEM_MOD_RANGED_ATTACK_POWER_SHORT"] = out.get("ITEM_MOD_RANGED_ATTACK_POWER_SHORT", 0.0) + float(m.group(1))
        m = FERAL_AP_RE.search(desc)
        if m:
            out["ITEM_MOD_FERAL_ATTACK_POWER_SHORT"] = out.get("ITEM_MOD_FERAL_ATTACK_POWER_SHORT", 0.0) + float(m.group(1))
        m = MP5_RE.search(desc)
        if m:
            out["ITEM_MOD_MANA_REGENERATION_SHORT"] = out.get("ITEM_MOD_MANA_REGENERATION_SHORT", 0.0) + float(m.group(1))
    return out


def add_stats(target: Dict[str, float], source: Dict[str, float]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0.0) + float(value)


def item_stats_from_api(equipment_item: Dict[str, Any], wowhead: WowheadCache) -> Dict[str, float]:
    stats: Dict[str, float] = {}

    for st in equipment_item.get("stats", []) or []:
        stat_type = ((st.get("type") or {}).get("type") or "").upper()
        token = API_STAT_TYPE_MAP.get(stat_type)
        if token:
            stats[token] = stats.get(token, 0.0) + float(st.get("value") or 0.0)

    add_stats(stats, extract_spell_stat_hints(equipment_item))

    for gem_id in equipment_item.get("gem_item_ids", []) or []:
        if isinstance(gem_id, int):
            add_stats(stats, wowhead.get_stats(gem_id))

    for ench in equipment_item.get("enchantments", []) or []:
        source_item = ench.get("source_item") or {}
        source_id = source_item.get("id")
        if isinstance(source_id, int):
            add_stats(stats, wowhead.get_stats(source_id))
        else:
            display = (ench.get("display_string") or "").strip()
            m = re.search(r"\+(\d+)\s+Stamina", display, re.I)
            if m:
                stats["ITEM_MOD_STAMINA_SHORT"] = stats.get("ITEM_MOD_STAMINA_SHORT", 0.0) + float(m.group(1))
            m = re.search(r"\+(\d+)\s+Agility", display, re.I)
            if m:
                stats["ITEM_MOD_AGILITY_SHORT"] = stats.get("ITEM_MOD_AGILITY_SHORT", 0.0) + float(m.group(1))
            m = re.search(r"\+(\d+)\s+Strength", display, re.I)
            if m:
                stats["ITEM_MOD_STRENGTH_SHORT"] = stats.get("ITEM_MOD_STRENGTH_SHORT", 0.0) + float(m.group(1))
            m = re.search(r"\+(\d+)\s+Defense", display, re.I)
            if m:
                stats["ITEM_MOD_DEFENSE_SKILL_RATING_SHORT"] = stats.get(
                    "ITEM_MOD_DEFENSE_SKILL_RATING_SHORT", 0.0
                ) + float(m.group(1))

    item_id = equipment_item.get("item_id")
    if isinstance(item_id, int):
        socket_count = wowhead.get_socket_count(item_id)
        if socket_count > 0:
            # Lua scoring counts socket keys from GetItemStats to determine missing gems.
            stats["EMPTY_SOCKET_PRISMATIC"] = float(socket_count)

    return stats


def get_enchant_id(equipment_item: Dict[str, Any]) -> int:
    for ench in equipment_item.get("enchantments", []) or []:
        slot = ench.get("enchantment_slot") or {}
        if slot.get("type") == "PERMANENT" or slot.get("id") == 0:
            source_id = ((ench.get("source_item") or {}).get("id"))
            if isinstance(source_id, int) and source_id > 0:
                return source_id
            return 1
    return 0


def build_item_link(equipment_item: Dict[str, Any]) -> str:
    item_id = int(equipment_item.get("item_id") or 0)
    enchant_id = get_enchant_id(equipment_item)
    gems = [int(g) for g in (equipment_item.get("gem_item_ids") or []) if isinstance(g, int)]
    while len(gems) < 4:
        gems.append(0)
    return f"item:{item_id}:{enchant_id}:{gems[0]}:{gems[1]}:{gems[2]}:{gems[3]}"


def get_item_equip_loc(equipment_item: Dict[str, Any]) -> str:
    inv_type = ((equipment_item.get("inventory_type") or {}).get("type") or "").upper()
    return INVENTORY_TYPE_TO_EQUIP_LOC.get(inv_type, f"INVTYPE_{inv_type}" if inv_type else "")


def score_character(
    equipment_by_slot: Dict[int, Dict[str, Any]],
    class_token: str,
    profile_name: str,
    phase: int,
    wowhead: WowheadCache,
    lua_scorer: LuaScorer,
) -> Dict[str, Any]:
    item_links_by_slot: Dict[int, str] = {}
    item_stats_by_link: Dict[str, Dict[str, float]] = {}
    equip_loc_by_link: Dict[str, str] = {}
    item_meta_by_slot: Dict[int, Dict[str, Any]] = {}

    for slot_id, equipment_item in equipment_by_slot.items():
        item_link = build_item_link(equipment_item)
        item_links_by_slot[slot_id] = item_link
        item_stats_by_link[item_link] = item_stats_from_api(equipment_item, wowhead)
        equip_loc_by_link[item_link] = get_item_equip_loc(equipment_item)
        item_meta_by_slot[slot_id] = {
            "item_id": equipment_item.get("item_id"),
            "item_name": equipment_item.get("name"),
        }

    raw = lua_scorer.score_character(
        class_token=class_token,
        profile_name=profile_name,
        phase=phase,
        item_links_by_slot=item_links_by_slot,
        item_stats_by_link=item_stats_by_link,
        equip_loc_by_link=equip_loc_by_link,
    )

    details: Dict[int, Dict[str, Any]] = {}
    raw_details = raw.get("details") or {}
    for slot_id in SCORE_SLOTS:
        detail = raw_details.get(slot_id)
        if not detail:
            continue
        meta = item_meta_by_slot.get(slot_id, {})
        details[slot_id] = {
            "slot": SLOT_LABELS.get(slot_id, str(slot_id)),
            "item_id": detail.get("itemID") or meta.get("item_id"),
            "item_name": meta.get("item_name"),
            "label": detail.get("label"),
            "factor": float(detail.get("factor") or 0.0),
            "phase_scalar": float(detail.get("phaseScalar") or 0.0),
            "slot_weight": float(detail.get("slotWeight") or 0.0),
            "slot_score": float(detail.get("slotScore") or 0.0),
            "slot_max": float(detail.get("slotMax") or 0.0),
        }

    return {
        "score": int(raw.get("score") or 0),
        "max_score": int(raw.get("maxScore") or PHASE_TARGET.get(phase, 1800)),
        "percent": float(raw.get("percent") or 0.0),
        "sum_score": float(raw.get("sumScore") or 0.0),
        "sum_max": float(raw.get("sumMax") or 0.0),
        "bis_slot_count": int(raw.get("bisSlotCount") or 0),
        "total_slots": int(raw.get("totalSlots") or len(SCORE_SLOTS)),
        "details": details,
    }


def build_equipment_by_slot(equipment_list: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for itm in equipment_list:
        slot_type = (itm.get("slot_type") or (itm.get("slot") or {}).get("type") or "").upper()
        slot_id = SLOT_TYPE_TO_ID.get(slot_type)
        if slot_id:
            out[slot_id] = itm
    return out


def format_report(record: Dict[str, Any]) -> str:
    lines: List[str] = []
    meta = record["meta"]
    score = record["score"]
    sum_max = float(score.get("sum_max") or 0.0)
    max_score = float(score.get("max_score") or 0.0)
    lines.append(
        f"{meta['name']} ({meta['class_name']} - {meta['profile']}, {meta['realm']}, phase {meta['phase']}): "
        f"{score['score']}/{score['max_score']} ({score['percent'] * 100:.1f}%), "
        f"BiS anchors {score['bis_slot_count']}/{score['total_slots']}"
    )
    lines.append("  Legend: factor = item quality in that slot; slot = weighted slot progress.")
    lines.append("  Slot breakdown:")
    for slot_id in SCORE_SLOTS:
        d = score["details"].get(slot_id)
        if not d:
            continue
        item = d.get("item_name") or "(empty)"
        item_id = d.get("item_id")
        item_suffix = f" [{item_id}]" if item_id else ""
        slot_points = ((float(d["slot_score"]) / sum_max) * max_score) if sum_max > 0 and max_score > 0 else 0.0
        slot_max_points = ((float(d["slot_max"]) / sum_max) * max_score) if sum_max > 0 and max_score > 0 else 0.0
        lines.append(
            f"    - {d['slot']}: {item}{item_suffix} | {d['label']} | factor={d['factor']:.3f} | "
            f"slot={d['slot_score']:.3f}/{d['slot_max']:.3f} | item points={slot_points:.1f}/{slot_max_points:.1f}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Classic Armory profiles and calculate BiScore total + item-by-item breakdown."
    )
    parser.add_argument(
        "--character",
        action="append",
        default=[],
        help="Character entry in format '<url>|<profile>', e.g. 'https://.../Name|Protection'",
    )
    parser.add_argument("--phase", type=int, default=1, choices=[1, 2, 3, 4, 5])
    parser.add_argument("--data-dir", default="BiScore/data")
    parser.add_argument("--json-out", default=None, help="Optional path to write JSON output")
    args = parser.parse_args()

    entries: List[Tuple[str, str]]
    if args.character:
        entries = [parse_character_arg(v) for v in args.character]
    else:
        entries = DEFAULT_CHARACTERS

    queries: List[CharacterQuery] = []
    for url, profile in entries:
        region, flavor, realm, name = parse_character_url(url)
        queries.append(
            CharacterQuery(url=url, region=region, flavor=flavor, realm=realm, name=name, profile=profile)
        )

    client = HttpClient()
    wowhead = WowheadCache(client)

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    data_dir = pathlib.Path(args.data_dir)
    lua_scorer = LuaScorer(core_dir=repo_root / "BiScore/core", data_dir=data_dir)

    all_results: List[Dict[str, Any]] = []

    for query in queries:
        payload = {
            "region": query.region,
            "realm": query.realm,
            "name": query.name,
            "flavor": query.flavor,
        }

        char_resp = client.post_json("https://classic-armory.org/api/v1/character", payload)
        eq_resp = client.post_json("https://classic-armory.org/api/v1/character/equipment", payload)

        character = char_resp.get("character") or {}
        class_name = (character.get("class_name") or "").strip()
        class_token = CLASS_TOKEN_FROM_NAME.get(class_name.lower())
        if not class_token:
            raise ValueError(f"Unsupported class from API: '{class_name}' for {query.name}")

        equipment = eq_resp.get("equipment") or []
        equipment_by_slot = build_equipment_by_slot(equipment)

        score = score_character(
            equipment_by_slot=equipment_by_slot,
            class_token=class_token,
            profile_name=query.profile,
            phase=args.phase,
            wowhead=wowhead,
            lua_scorer=lua_scorer,
        )

        record = {
            "meta": {
                "url": query.url,
                "region": query.region,
                "flavor": query.flavor,
                "realm": query.realm,
                "name": query.name,
                "profile": query.profile,
                "class_name": class_name,
                "phase": args.phase,
            },
            "score": score,
        }
        all_results.append(record)

    for rec in all_results:
        print(format_report(rec))
        print()

    if args.json_out:
        out_path = pathlib.Path(args.json_out)
        out_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        print(f"Wrote JSON output to {out_path.resolve()}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        raise
