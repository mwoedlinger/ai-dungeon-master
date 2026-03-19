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

    # Parse legendary actions
    legendary_actions = []
    for la in data.get("legendary_actions", []):
        legendary_actions.append({
            "name": la.get("name", "Unknown"),
            "description": la.get("desc", ""),
            "cost": 1,  # default cost; multi-cost actions noted in description
        })
    # Standard: 3 legendary actions per round if any are defined
    la_per_round = 3 if legendary_actions else 0

    # Parse legendary resistances from special abilities
    legendary_resistances = 0
    for ability in data.get("special_abilities", []):
        if "legendary resistance" in ability.get("name", "").lower():
            # Typically "Legendary Resistance (3/Day)" — extract the number
            lr_match = re.search(r"\((\d+)/[Dd]ay\)", ability.get("name", ""))
            legendary_resistances = int(lr_match.group(1)) if lr_match else 3

    # Parse lair actions
    lair_actions = []
    has_lair = bool(data.get("lair_actions"))

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
        "legendary_actions": legendary_actions,
        "legendary_actions_per_round": la_per_round,
        "legendary_actions_remaining": la_per_round,
        "legendary_resistances": legendary_resistances,
        "legendary_resistances_remaining": legendary_resistances,
        "lair_actions": lair_actions,
        "has_lair": has_lair,
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


# Manual overrides for spells that need specific resolution not inferable from API data.
# Keyed by spell name exactly as it appears in the SRD.
_SPELL_OVERRIDES: dict[str, dict] = {
    # Level 4
    "Banishment": {"resolution": "save_effect", "save_ability": "CHA", "condition_effect": "banished"},
    "Greater Invisibility": {"resolution": "buff", "description": "Target is invisible. Attacks against it have disadvantage; its attacks have advantage."},
    "Dimension Door": {"resolution": "buff", "description": "Teleport up to 500 feet to a visible or described location."},
    # Level 5
    "Wall of Force": {"resolution": "buff", "description": "An invisible wall of force springs into existence. Nothing can physically pass through it."},
    "Hold Monster": {"resolution": "save_effect", "save_ability": "WIS", "condition_effect": "paralyzed"},
    # Level 6
    "Heal": {"resolution": "healing"},
    # Level 7
    "Teleport": {"resolution": "buff", "description": "Teleport yourself and up to 8 willing creatures to a destination you're familiar with."},
    "Forcecage": {"resolution": "buff", "description": "An immobile, invisible, cube-shaped prison of force springs into existence around a point."},
    # Level 8
    "Power Word Stun": {"resolution": "save_effect", "condition_effect": "stunned",
                         "description": "Stun a creature with 150 HP or fewer (no save). It makes CON saves at end of each turn to end."},
    # Level 9
    "Power Word Kill": {"resolution": "auto_damage", "damage_dice": "0", "damage_type": "force",
                         "description": "Kill a creature with 100 HP or fewer instantly. No save."},
    "Wish": {"resolution": "buff", "description": "The mightiest spell a mortal can cast. Duplicate any 8th-level or lower spell, or create another effect."},
    "Meteor Swarm": {"resolution": "save_damage", "save_ability": "DEX", "damage_dice": "40d6",
                      "damage_type": "fire"},
}


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

    # Cantrip scaling — extract damage_at_character_level
    cantrip_scaling = None
    if level == 0:
        char_dmg = (dmg.get("damage_at_character_level") or {}) if dmg else {}
        if char_dmg:
            cantrip_scaling = {int(k): v for k, v in char_dmg.items()}

    # Save negates (0 damage on success, e.g. Disintegrate)
    save_negates = False
    dc_success = dc_info.get("dc_success", "half") if dc_info else "half"
    if dc_success == "none":
        save_negates = True

    # Flat healing (e.g. Heal: 70hp, not dice-based)
    flat_healing = None
    if healing_dice and healing_dice.isdigit():
        flat_healing = int(healing_dice)
        healing_dice = None

    # Upcast pattern — infer from higher_level text
    upcast_pattern = "damage"
    hl_text = " ".join(data.get("higher_level", [])).lower()
    if "additional creature" in hl_text or "additional target" in hl_text or "one more creature" in hl_text:
        upcast_pattern = "targets"
    elif "duration" in hl_text and ("hour" in hl_text or "minute" in hl_text):
        upcast_pattern = "duration"
    elif flat_healing is not None and ("increases by" in hl_text or "amount of healing" in hl_text):
        upcast_pattern = "flat_healing"

    # Upcast bonus for flat healing spells (e.g., Heal: +10 per level)
    if flat_healing is not None and upcast_bonus is None and heal_levels:
        sorted_keys = sorted(heal_levels.keys(), key=int)
        if len(sorted_keys) >= 2:
            v1 = heal_levels[sorted_keys[0]]
            v2 = heal_levels[sorted_keys[1]]
            if v1.isdigit() and v2.isdigit():
                diff = int(v2) - int(v1)
                if diff > 0:
                    upcast_bonus = f"+{diff} per level"
                    upcast_pattern = "flat_healing"

    # Apply manual overrides for specific spells
    spell_name = data.get("name", "Unknown")
    if spell_name in _SPELL_OVERRIDES:
        override = _SPELL_OVERRIDES[spell_name]
        resolution = override.get("resolution", resolution)
        if "damage_dice" in override:
            damage_dice = override["damage_dice"]
        if "damage_type" in override:
            damage_type = override["damage_type"]
        if "save_ability" in override:
            save_ability = override["save_ability"]
        if "condition_effect" in override:
            condition_effect = override["condition_effect"]
        if "save_negates" in override:
            save_negates = override["save_negates"]
        if "description" in override:
            buff_effect = override["description"]

    return SpellData(
        name=spell_name,
        level=level,
        resolution=resolution,
        casting_time=casting_time,
        concentration=concentration,
        damage_dice=damage_dice,
        damage_type=damage_type,
        save_ability=save_ability,
        save_negates=save_negates,
        healing_dice=healing_dice,
        flat_healing=flat_healing,
        buff_effect=buff_effect,
        duration_rounds=duration_rounds,
        upcast_bonus=upcast_bonus,
        upcast_pattern=upcast_pattern,
        cantrip_scaling=cantrip_scaling,
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


def _api_magic_item_to_internal(data: dict) -> dict:
    """Convert dnd5eapi.co magic-item to a summary dict."""
    desc = " ".join(data.get("desc", []))
    rarity_obj = data.get("rarity", {})
    rarity = rarity_obj.get("name", "Unknown") if isinstance(rarity_obj, dict) else str(rarity_obj)

    # Try to infer bonus from description
    bonus = 0
    import re as _re
    bonus_match = _re.search(r"\+(\d)\s+bonus", desc.lower())
    if bonus_match:
        bonus = int(bonus_match.group(1))

    # Infer item type from equipment_category or description
    cat = data.get("equipment_category", {})
    cat_name = cat.get("name", "") if isinstance(cat, dict) else ""
    desc_lower = desc.lower()
    if "armor" in cat_name.lower() or "armor" in desc_lower[:100]:
        item_type = "armor"
    elif "weapon" in cat_name.lower() or "sword" in data.get("name", "").lower() or "weapon" in desc_lower[:100]:
        item_type = "weapon"
    elif "potion" in data.get("name", "").lower():
        item_type = "potion"
    elif "scroll" in data.get("name", "").lower():
        item_type = "scroll"
    elif "ring" in data.get("name", "").lower():
        item_type = "ring"
    elif "wand" in data.get("name", "").lower():
        item_type = "wand"
    elif "staff" in data.get("name", "").lower():
        item_type = "staff"
    elif "rod" in data.get("name", "").lower():
        item_type = "rod"
    else:
        item_type = "wondrous"

    requires_attunement = "requires attunement" in desc_lower

    return {
        "name": data.get("name", "Unknown"),
        "item_type": item_type,
        "bonus": bonus,
        "rarity": rarity.lower().replace(" ", "_"),
        "requires_attunement": requires_attunement,
        "description": desc,
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


_mem_magic_items: dict[str, dict] = {}


def get_magic_item(name: str) -> dict | None:
    """Get a magic item by name. Returns a summary dict or None."""
    key = name.lower()
    if key in _mem_magic_items:
        return _mem_magic_items[key]

    index = _to_index(name)
    raw = _get_raw("magic-items", index)
    if raw is not None:
        internal = _api_magic_item_to_internal(raw)
        _mem_magic_items[key] = internal
        return internal

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

        case "magic-items":
            item = get_magic_item(query)
            if item:
                return {"success": True, **item}
            matches = search_srd("magic-items", query)
            if matches:
                return {"success": False, "error": f"Magic item '{query}' not found.", "suggestions": [m["name"] for m in matches[:10]]}
            return {"success": False, "error": f"Magic item '{query}' not found."}

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
            return {"success": False, "error": f"Unknown SRD category: {category!r}. Use: monsters, spells, equipment, magic-items, classes, races, conditions, skills, features."}


def clear_caches() -> None:
    """Clear all in-memory caches. Useful for testing."""
    _mem_monsters.clear()
    _mem_spells.clear()
    _mem_weapons.clear()
    _mem_armor.clear()
    _mem_magic_items.clear()
    _mem_indexes.clear()
