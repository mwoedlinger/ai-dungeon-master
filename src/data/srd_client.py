"""SRD data client — API + file cache.

Lookup order:
  1. In-memory cache (populated during session)
  2. Local file cache (src/data/srd/cache/{category}/{index}.json)
  3. Remote API (dnd5eapi.co)

The SRD data is immutable, so cache entries never expire.
Run `python scripts/fetch_srd_data.py` to pre-populate the cache for offline play.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.models.character import Armor, Weapon
from src.models.monster import Monster, MonsterAction
from src.models.spells import SpellData

logger = logging.getLogger(__name__)

_API_BASE = "https://www.dnd5eapi.co/api/2014"
_CACHE_DIR = Path(__file__).parent / "srd" / "cache"

# In-memory caches (populated lazily)
_mem_monsters: dict[str, dict] = {}
_mem_spells: dict[str, SpellData] = {}
_mem_weapons: dict[str, dict] = {}
_mem_armor: dict[str, dict] = {}
_mem_indexes: dict[str, list[dict]] = {}  # category → [{index, name}, ...]


# ---------------------------------------------------------------------------
# Low-level cache / fetch
# ---------------------------------------------------------------------------

def _cache_path(category: str, index: str) -> Path:
    return _CACHE_DIR / category / f"{index}.json"


def _read_cache(category: str, index: str) -> dict | None:
    path = _cache_path(category, index)
    if path.exists():
        return json.loads(path.read_text())
    return None


def _write_cache(category: str, index: str, data: dict) -> None:
    path = _cache_path(category, index)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _fetch_api(endpoint: str) -> dict | None:
    """Fetch from the 5e SRD API. Returns None if httpx unavailable or request fails."""
    try:
        import httpx  # noqa: F811 — optional dependency
    except ImportError:
        logger.debug("httpx not installed — skipping API fetch")
        return None
    try:
        resp = httpx.get(f"{_API_BASE}/{endpoint}", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug("SRD API fetch failed for %s: %s", endpoint, e)
        return None


def _get_raw(category: str, index: str) -> dict | None:
    """Get raw API-format data: file cache → API → None."""
    cached = _read_cache(category, index)
    if cached is not None:
        return cached
    data = _fetch_api(f"{category}/{index}")
    if data is not None:
        _write_cache(category, index, data)
        return data
    return None


def _to_index(name: str) -> str:
    """Convert a display name to an API index: 'Ancient Red Dragon' → 'ancient-red-dragon'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ---------------------------------------------------------------------------
# API → internal model converters
# ---------------------------------------------------------------------------

def _parse_speed(speed: dict | str) -> int:
    """Extract walk speed as int from API speed data."""
    if isinstance(speed, dict):
        walk = speed.get("walk", "30 ft.")
    else:
        walk = str(speed)
    m = re.search(r"(\d+)", str(walk))
    return int(m.group(1)) if m else 30


def _parse_ac(armor_class: list | int) -> int:
    """Extract AC from API armor_class field."""
    if isinstance(armor_class, int):
        return armor_class
    if isinstance(armor_class, list) and armor_class:
        entry = armor_class[0]
        if isinstance(entry, dict):
            return entry.get("value", 10)
        return int(entry)
    return 10


_CR_TO_PROF: dict[float, int] = {
    0: 2, 0.125: 2, 0.25: 2, 0.5: 2,
    **{float(i): 2 + (i - 1) // 4 for i in range(1, 31)},
}


def _api_monster_to_internal(data: dict) -> dict:
    """Convert dnd5eapi.co monster to our internal Character-compatible dict."""
    index = data.get("index", "unknown")
    cr = data.get("challenge_rating", 0)
    prof = _CR_TO_PROF.get(float(cr), 2)

    # Actions
    actions = []
    first_weapon: dict | None = None
    for act in data.get("actions", []):
        damage_dice = None
        damage_type = None
        attack_bonus = None

        if act.get("attack_bonus"):
            attack_bonus = act["attack_bonus"]

        # Parse damage from API format
        if act.get("damage"):
            for dmg in act["damage"]:
                dd = dmg.get("damage_dice")
                dt = dmg.get("damage_type", {})
                if isinstance(dt, dict):
                    dt = dt.get("name", "")
                if dd:
                    damage_dice = dd
                    damage_type = dt.lower() if dt else None
                    break

        # Determine action type from usage or default
        action_type = "action"

        action = {
            "name": act.get("name", "Unknown"),
            "description": act.get("desc", ""),
            "action_type": action_type,
            "attack_bonus": attack_bonus,
            "damage_dice": damage_dice,
            "damage_type": damage_type,
            "save_dc": None,
            "save_ability": None,
            "recharge": None,
            "available": True,
        }

        # Parse save DC if present
        if act.get("dc"):
            dc_info = act["dc"]
            action["save_dc"] = dc_info.get("dc_value")
            dc_type = dc_info.get("dc_type", {})
            if isinstance(dc_type, dict):
                action["save_ability"] = dc_type.get("index", "").upper()[:3]

        # Parse recharge
        if act.get("usage"):
            usage = act["usage"]
            if usage.get("type") == "recharge on roll":
                action["recharge"] = f"{usage.get('min_value', 6)}-6"

        actions.append(action)

        # Build weapon from first damage-dealing action
        if first_weapon is None and damage_dice:
            props: list[str] = []
            desc = act.get("desc", "").lower()
            if "ranged" in desc:
                props.append("ranged")
            if "finesse" in desc:
                props.append("finesse")
            first_weapon = {
                "name": act["name"],
                "damage_dice": damage_dice,
                "damage_type": damage_type or "slashing",
                "properties": props,
                "range_normal": None,
                "range_long": None,
                "attack_bonus_override": None,
            }

    # Special abilities
    special_traits = []
    for ability in data.get("special_abilities", []):
        name = ability.get("name", "")
        desc = ability.get("desc", "")
        short = desc[:120] + "..." if len(desc) > 120 else desc
        special_traits.append(f"{name}: {short}")

    # Skill proficiencies
    skill_profs = []
    for prof_entry in data.get("proficiencies", []):
        p = prof_entry.get("proficiency", {})
        p_index = p.get("index", "")
        if p_index.startswith("skill-"):
            skill_name = p_index.replace("skill-", "").replace("-", " ").title()
            skill_profs.append(skill_name)

    # Damage resistances/immunities/condition immunities
    damage_resistances = [
        r if isinstance(r, str) else r.get("name", str(r))
        for r in data.get("damage_resistances", [])
    ]
    damage_immunities = [
        r if isinstance(r, str) else r.get("name", str(r))
        for r in data.get("damage_immunities", [])
    ]
    condition_immunities = [
        c.get("name", str(c)).lower() if isinstance(c, dict) else str(c).lower()
        for c in data.get("condition_immunities", [])
    ]

    hit_dice_str = data.get("hit_dice", "1d8")
    hd_match = re.search(r"d(\d+)", hit_dice_str)
    hit_die = f"d{hd_match.group(1)}" if hd_match else "d8"

    monster_type = data.get("type", "monster").capitalize()

    return {
        "id": index,
        "name": data.get("name", index),
        "race": monster_type,
        "class_name": "monster",
        "level": max(1, int(cr)) if cr >= 1 else 1,
        "xp": 0,
        "ability_scores": {
            "STR": data.get("strength", 10),
            "DEX": data.get("dexterity", 10),
            "CON": data.get("constitution", 10),
            "INT": data.get("intelligence", 10),
            "WIS": data.get("wisdom", 10),
            "CHA": data.get("charisma", 10),
        },
        "hp": data.get("hit_points", 10),
        "max_hp": data.get("hit_points", 10),
        "temp_hp": 0,
        "ac": _parse_ac(data.get("armor_class", 10)),
        "speed": _parse_speed(data.get("speed", {})),
        "proficiency_bonus": prof,
        "skill_proficiencies": skill_profs,
        "weapon_proficiencies": [],
        "armor_proficiencies": [],
        "saving_throw_proficiencies": [],
        "spell_slots": {},
        "max_spell_slots": {},
        "spellcasting_ability": None,
        "known_spells": [],
        "hit_dice_remaining": 0,
        "hit_die_type": hit_die,
        "class_resources": {},
        "weapons": [first_weapon] if first_weapon else [],
        "armor": None,
        "shield": False,
        "inventory": [],
        "conditions": [],
        "concentration": None,
        "death_saves": {"successes": 0, "failures": 0},
        "is_player": False,
        "challenge_rating": float(cr),
        "xp_value": data.get("xp", 0),
        "actions": actions,
        "special_traits": special_traits,
        "damage_resistances": damage_resistances,
        "damage_immunities": damage_immunities,
        "condition_immunities": condition_immunities,
    }


def _infer_resolution(data: dict) -> str:
    """Infer spell resolution type from API data."""
    # Explicit healing spells (heal_at_slot_level is definitive)
    if data.get("heal_at_slot_level"):
        return "healing"
    if data.get("dc"):
        if data.get("damage") and data["damage"].get("damage_at_slot_level"):
            return "save_damage"
        desc_lower = " ".join(data.get("desc", [])).lower()
        if any(kw in desc_lower for kw in ["charmed", "frightened", "paralyzed", "restrained", "stunned", "incapacitated", "prone"]):
            return "save_effect"
        return "save_effect"
    if data.get("attack_type") in ("ranged", "melee"):
        return "attack_roll"
    if data.get("damage") and data["damage"].get("damage_at_slot_level"):
        return "auto_damage"
    desc_lower = " ".join(data.get("desc", [])).lower()
    # Only classify as healing if the spell's primary purpose is healing
    if any(kw in desc_lower for kw in ["regain", "heal"]) and "hit points" in desc_lower and data.get("level", 0) <= 5:
        return "healing"
    if any(kw in desc_lower for kw in ["bonus to", "speed is doubled", "advantage on", "invisible", "teleport"]):
        return "buff"
    return "narrative"


def _api_spell_to_internal(data: dict) -> SpellData:
    """Convert dnd5eapi.co spell to our SpellData model."""
    level = data.get("level", 0)
    resolution = _infer_resolution(data)

    # Casting time
    raw_ct = data.get("casting_time", "1 action").lower()
    if "bonus" in raw_ct:
        casting_time = "bonus_action"
    elif "reaction" in raw_ct:
        casting_time = "reaction"
    else:
        casting_time = "action"

    concentration = data.get("concentration", False)

    # Damage
    damage_dice = None
    damage_type = None
    dmg = data.get("damage", {})
    if dmg:
        dt = dmg.get("damage_type", {})
        if isinstance(dt, dict):
            damage_type = dt.get("name", "").lower() or None
        slot_levels = dmg.get("damage_at_slot_level") or dmg.get("damage_at_character_level") or {}
        if slot_levels:
            base_key = str(level) if level > 0 else min(slot_levels.keys(), key=int, default="1")
            damage_dice = slot_levels.get(base_key)

    # Save ability
    save_ability = None
    dc_info = data.get("dc", {})
    if dc_info:
        dc_type = dc_info.get("dc_type", {})
        if isinstance(dc_type, dict):
            save_ability = dc_type.get("index", "").upper()[:3] or None

    # Healing
    healing_dice = None
    heal_levels = data.get("heal_at_slot_level", {})
    if heal_levels:
        base_key = str(level) if str(level) in heal_levels else min(heal_levels.keys(), key=int, default="1")
        healing_dice = heal_levels.get(base_key)
        resolution = "healing"

    # Duration
    duration_rounds = None
    raw_dur = data.get("duration", "Instantaneous")
    if "minute" in raw_dur.lower():
        m = re.search(r"(\d+)", raw_dur)
        if m:
            duration_rounds = int(m.group(1)) * 10  # 1 min ≈ 10 rounds
    elif "hour" in raw_dur.lower():
        duration_rounds = 600  # ~1 hour in rounds
    elif "round" in raw_dur.lower():
        m = re.search(r"(\d+)", raw_dur)
        duration_rounds = int(m.group(1)) if m else 1

    # Upcast bonus
    upcast_bonus = None
    slot_dmg = (dmg.get("damage_at_slot_level") or {}) if dmg else {}
    if level > 0 and len(slot_dmg) >= 2:
        keys = sorted(slot_dmg.keys(), key=int)
        base = slot_dmg.get(keys[0], "")
        next_level = slot_dmg.get(keys[1], "")
        if base and next_level:
            upcast_bonus = _compute_upcast_diff(base, next_level)
    if upcast_bonus is None and data.get("higher_level"):
        hl_text = " ".join(data["higher_level"]).lower()
        dice_match = re.search(r"(\d+d\d+)\s+(?:per|for each|additional)", hl_text)
        if dice_match:
            upcast_bonus = f"+{dice_match.group(1)} per level"

    # Buff effect
    buff_effect = None
    if resolution == "buff":
        buff_effect = " ".join(data.get("desc", []))[:200]

    aoe = data.get("area_of_effect") is not None

    # Condition effect
    condition_effect = None
    if resolution == "save_effect":
        desc_lower = " ".join(data.get("desc", [])).lower()
        for cond in ["paralyzed", "charmed", "frightened", "restrained", "stunned",
                      "incapacitated", "blinded", "deafened", "prone", "poisoned", "petrified"]:
            if cond in desc_lower:
                condition_effect = cond
                break

    return SpellData(
        name=data.get("name", "Unknown"),
        level=level,
        resolution=resolution,
        casting_time=casting_time,
        concentration=concentration,
        damage_dice=damage_dice,
        damage_type=damage_type,
        save_ability=save_ability,
        healing_dice=healing_dice,
        buff_effect=buff_effect,
        duration_rounds=duration_rounds,
        upcast_bonus=upcast_bonus,
        description=" ".join(data.get("desc", [])),
        aoe=aoe,
        condition_effect=condition_effect,
    )


def _compute_upcast_diff(base: str, next_level: str) -> str | None:
    """Compute upcast bonus from two slot-level damage strings, e.g. '8d6' vs '9d6'."""
    m_base = re.match(r"(\d+)d(\d+)", base)
    m_next = re.match(r"(\d+)d(\d+)", next_level)
    if m_base and m_next:
        n_diff = int(m_next.group(1)) - int(m_base.group(1))
        die = m_next.group(2)
        if n_diff > 0:
            return f"+{n_diff}d{die} per level"
    return None


def _api_weapon_to_internal(data: dict) -> dict:
    """Convert dnd5eapi.co equipment (weapon) to our Weapon-compatible dict."""
    damage = data.get("damage", {})
    damage_dice = damage.get("damage_dice", "1d4")
    dt = damage.get("damage_type", {})
    damage_type = dt.get("name", "slashing").lower() if isinstance(dt, dict) else "slashing"

    props = []
    for p in data.get("properties", []):
        p_name = p.get("index", "") if isinstance(p, dict) else str(p)
        if p_name:
            props.append(p_name.replace("-", " "))

    range_normal = None
    range_long = None
    rng = data.get("range", {})
    if rng:
        range_normal = rng.get("normal")
        range_long = rng.get("long")

    if data.get("weapon_range", "").lower() == "ranged" and "ranged" not in props:
        props.append("ranged")

    return {
        "name": data.get("name", "Unknown"),
        "damage_dice": damage_dice,
        "damage_type": damage_type,
        "properties": props,
        "range_normal": range_normal,
        "range_long": range_long,
        "attack_bonus_override": None,
    }


def _api_armor_to_internal(data: dict) -> dict:
    """Convert dnd5eapi.co equipment (armor) to our Armor-compatible dict."""
    ac_info = data.get("armor_class", {})
    base_ac = ac_info.get("base", 10)
    dex_bonus = ac_info.get("dex_bonus", False)
    max_bonus = ac_info.get("max_bonus")  # None = unlimited, 2 = medium

    if data.get("armor_category", "").lower() == "shield":
        armor_type = "shield"
        base_ac = 2  # shields add +2
    elif max_bonus == 2:
        armor_type = "medium"
    elif dex_bonus:
        armor_type = "light"
    else:
        armor_type = "heavy"

    return {
        "name": data.get("name", "Unknown"),
        "base_ac": base_ac,
        "armor_type": armor_type,
        "stealth_disadvantage": data.get("stealth_disadvantage", False),
        "strength_requirement": data.get("str_minimum", None) or None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_srd_data() -> None:
    """No-op kept for backward compat. Data is loaded lazily from cache/API."""
    pass


def get_monster_template(monster_id: str) -> Monster:
    """Get a fresh Monster instance by SRD index (e.g. 'goblin', 'ancient-red-dragon').

    Lookup: memory → file cache → API.
    """
    index = _to_index(monster_id)

    # Check memory cache
    if index in _mem_monsters:
        return Monster.model_validate(json.loads(json.dumps(_mem_monsters[index])))

    # Try file cache / API
    raw = _get_raw("monsters", index)
    if raw is not None:
        internal = _api_monster_to_internal(raw)
        _mem_monsters[index] = internal
        return Monster.model_validate(json.loads(json.dumps(internal)))

    raise KeyError(f"Monster template not found: {monster_id!r}")


def get_spell(name: str) -> SpellData | None:
    """Get a spell by name (case-insensitive).

    Lookup: memory → file cache → API.
    """
    key = name.lower()

    if key in _mem_spells:
        return _mem_spells[key]

    index = _to_index(name)
    raw = _get_raw("spells", index)
    if raw is not None:
        spell = _api_spell_to_internal(raw)
        _mem_spells[key] = spell
        return spell

    return None


def get_weapon(name: str) -> Weapon | None:
    """Get a weapon by name."""
    key = name.lower()

    if key in _mem_weapons:
        return Weapon.model_validate(_mem_weapons[key])

    index = _to_index(name)
    raw = _get_raw("equipment", index)
    if raw is not None and raw.get("equipment_category", {}).get("index") == "weapon":
        internal = _api_weapon_to_internal(raw)
        _mem_weapons[key] = internal
        return Weapon.model_validate(internal)

    return None


def get_armor(name: str) -> Armor | None:
    """Get armor by name."""
    key = name.lower()

    if key in _mem_armor:
        return Armor.model_validate(_mem_armor[key])

    index = _to_index(name)
    raw = _get_raw("equipment", index)
    if raw is not None and raw.get("equipment_category", {}).get("index") == "armor":
        internal = _api_armor_to_internal(raw)
        _mem_armor[key] = internal
        return Armor.model_validate(internal)

    return None


def get_index(category: str) -> list[dict[str, str]]:
    """Get the full index of a category (monsters, spells, equipment, etc.).

    Returns list of {index, name} dicts.
    """
    if category in _mem_indexes:
        return _mem_indexes[category]

    cached = _read_cache("_indexes", category)
    if cached is not None:
        _mem_indexes[category] = cached
        return cached

    data = _fetch_api(category)
    if data is not None:
        results = data.get("results", [])
        entries = [{"index": r["index"], "name": r["name"]} for r in results]
        _write_cache("_indexes", category, entries)
        _mem_indexes[category] = entries
        return entries

    return []


def search_srd(category: str, query: str = "") -> list[dict[str, str]]:
    """Search SRD entities by name within a category.

    Returns matching {index, name} entries. Empty query returns all.
    """
    entries = get_index(category)
    if not query:
        return entries
    q = query.lower()
    return [e for e in entries if q in e["name"].lower()]


def lookup_srd(category: str, query: str) -> dict[str, Any]:
    """Look up any SRD entity and return a human-readable summary.

    Used by the LLM tool to get data on demand during gameplay.
    """
    index = _to_index(query)

    match category:
        case "monsters":
            try:
                monster = get_monster_template(index)
                return {
                    "success": True,
                    "name": monster.name,
                    "type": monster.race,
                    "cr": monster.challenge_rating,
                    "xp": monster.xp_value,
                    "ac": monster.ac,
                    "hp": monster.max_hp,
                    "speed": monster.speed,
                    "abilities": monster.ability_scores.model_dump(),
                    "actions": [a.model_dump() for a in monster.actions],
                    "special_traits": monster.special_traits,
                    "damage_resistances": monster.damage_resistances,
                    "damage_immunities": monster.damage_immunities,
                    "condition_immunities": monster.condition_immunities,
                }
            except KeyError:
                matches = search_srd("monsters", query)
                if matches:
                    return {"success": False, "error": f"Monster '{query}' not found.", "suggestions": [m["name"] for m in matches[:10]]}
                return {"success": False, "error": f"Monster '{query}' not found."}

        case "spells":
            spell = get_spell(query)
            if spell:
                return {"success": True, **spell.model_dump()}
            matches = search_srd("spells", query)
            if matches:
                return {"success": False, "error": f"Spell '{query}' not found.", "suggestions": [s["name"] for s in matches[:10]]}
            return {"success": False, "error": f"Spell '{query}' not found."}

        case "equipment":
            weapon = get_weapon(query)
            if weapon:
                return {"success": True, "type": "weapon", **weapon.model_dump()}
            armor = get_armor(query)
            if armor:
                return {"success": True, "type": "armor", **armor.model_dump()}
            raw = _get_raw("equipment", index)
            if raw:
                return {
                    "success": True,
                    "name": raw.get("name"),
                    "category": raw.get("equipment_category", {}).get("name"),
                    "cost": raw.get("cost"),
                    "weight": raw.get("weight"),
                    "description": " ".join(raw.get("desc", [])),
                }
            matches = search_srd("equipment", query)
            if matches:
                return {"success": False, "error": f"Equipment '{query}' not found.", "suggestions": [e["name"] for e in matches[:10]]}
            return {"success": False, "error": f"Equipment '{query}' not found."}

        case "classes" | "races" | "conditions" | "skills" | "features":
            raw = _get_raw(category, index)
            if raw:
                return {
                    "success": True,
                    "name": raw.get("name"),
                    "index": raw.get("index"),
                    "description": " ".join(raw.get("desc", [])) if raw.get("desc") else raw.get("brief", ""),
                    "data": {k: v for k, v in raw.items() if k not in ("url", "_id")},
                }
            matches = search_srd(category, query)
            if matches:
                return {"success": False, "error": f"'{query}' not found in {category}.", "suggestions": [e["name"] for e in matches[:10]]}
            return {"success": False, "error": f"'{query}' not found in {category}."}

        case _:
            return {"success": False, "error": f"Unknown SRD category: {category!r}. Use: monsters, spells, equipment, classes, races, conditions, skills, features."}


def clear_caches() -> None:
    """Clear all in-memory caches. Useful for testing."""
    _mem_monsters.clear()
    _mem_spells.clear()
    _mem_weapons.clear()
    _mem_armor.clear()
    _mem_indexes.clear()
