"""Tests for SRD client — converters, cache, and fallback logic."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data.srd_client import (
    _api_armor_to_internal,
    _api_monster_to_internal,
    _api_spell_to_internal,
    _api_weapon_to_internal,
    _compute_upcast_diff,
    _parse_ac,
    _parse_speed,
    _to_index,
    clear_caches,
    get_armor,
    get_monster_template,
    get_spell,
    get_weapon,
    load_srd_data,
    lookup_srd,
)
from src.models.character import Armor, Weapon
from src.models.monster import Monster
from src.models.spells import SpellData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fresh_caches():
    """Reset all caches before each test."""
    clear_caches()
    yield
    clear_caches()


# ---------------------------------------------------------------------------
# Name/index conversion
# ---------------------------------------------------------------------------

def test_to_index():
    assert _to_index("Ancient Red Dragon") == "ancient-red-dragon"
    assert _to_index("Goblin") == "goblin"
    assert _to_index("Mage Hand") == "mage-hand"
    assert _to_index("longsword") == "longsword"


# ---------------------------------------------------------------------------
# AC / Speed parsing
# ---------------------------------------------------------------------------

def test_parse_ac_list():
    assert _parse_ac([{"type": "natural", "value": 15}]) == 15

def test_parse_ac_int():
    assert _parse_ac(13) == 13

def test_parse_ac_empty():
    assert _parse_ac([]) == 10

def test_parse_speed_dict():
    assert _parse_speed({"walk": "30 ft."}) == 30

def test_parse_speed_string():
    assert _parse_speed("40 ft.") == 40


# ---------------------------------------------------------------------------
# Monster converter
# ---------------------------------------------------------------------------

SAMPLE_API_MONSTER = {
    "index": "goblin",
    "name": "Goblin",
    "type": "humanoid",
    "challenge_rating": 0.25,
    "xp": 50,
    "hit_points": 7,
    "hit_dice": "2d6",
    "armor_class": [{"type": "armor", "value": 15}],
    "speed": {"walk": "30 ft."},
    "strength": 8,
    "dexterity": 14,
    "constitution": 10,
    "intelligence": 10,
    "wisdom": 8,
    "charisma": 8,
    "proficiencies": [
        {"value": 6, "proficiency": {"index": "skill-stealth", "name": "Skill: Stealth"}},
    ],
    "damage_resistances": [],
    "damage_immunities": [],
    "condition_immunities": [],
    "actions": [
        {
            "name": "Scimitar",
            "desc": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target.",
            "attack_bonus": 4,
            "damage": [{"damage_dice": "1d6+2", "damage_type": {"index": "slashing", "name": "Slashing"}}],
        },
    ],
    "special_abilities": [
        {"name": "Nimble Escape", "desc": "The goblin can take the Disengage or Hide action as a bonus action."},
    ],
}


def test_api_monster_to_internal():
    result = _api_monster_to_internal(SAMPLE_API_MONSTER)
    assert result["name"] == "Goblin"
    assert result["ac"] == 15
    assert result["hp"] == 7
    assert result["ability_scores"]["DEX"] == 14
    assert result["challenge_rating"] == 0.25
    assert result["xp_value"] == 50
    assert len(result["actions"]) == 1
    assert result["actions"][0]["attack_bonus"] == 4
    assert result["actions"][0]["damage_dice"] == "1d6+2"
    assert "Stealth" in result["skill_proficiencies"]
    assert len(result["special_traits"]) == 1
    assert "Nimble Escape" in result["special_traits"][0]


def test_api_monster_validates_as_model():
    internal = _api_monster_to_internal(SAMPLE_API_MONSTER)
    monster = Monster.model_validate(internal)
    assert monster.name == "Goblin"
    assert monster.ac == 15


# ---------------------------------------------------------------------------
# Spell converter
# ---------------------------------------------------------------------------

SAMPLE_API_SPELL = {
    "index": "fireball",
    "name": "Fireball",
    "level": 3,
    "casting_time": "1 action",
    "range": "150 feet",
    "concentration": False,
    "duration": "Instantaneous",
    "desc": ["A bright streak flashes from your pointing finger and blossoms into an explosion of flame."],
    "higher_level": ["When you cast this spell using a spell slot of 4th level or higher, the damage increases by 1d6 for each slot level above 3rd."],
    "damage": {
        "damage_type": {"index": "fire", "name": "Fire"},
        "damage_at_slot_level": {"3": "8d6", "4": "9d6", "5": "10d6"},
    },
    "dc": {"dc_type": {"index": "dex", "name": "DEX"}, "dc_success": "half"},
    "area_of_effect": {"type": "sphere", "size": 20},
    "school": {"index": "evocation", "name": "Evocation"},
    "classes": [{"index": "sorcerer"}, {"index": "wizard"}],
}


def test_api_spell_to_internal():
    spell = _api_spell_to_internal(SAMPLE_API_SPELL)
    assert isinstance(spell, SpellData)
    assert spell.name == "Fireball"
    assert spell.level == 3
    assert spell.resolution == "save_damage"
    assert spell.damage_dice == "8d6"
    assert spell.damage_type == "fire"
    assert spell.save_ability == "DEX"
    assert spell.aoe is True
    assert spell.casting_time == "action"
    assert spell.concentration is False
    assert spell.upcast_bonus == "+1d6 per level"


SAMPLE_API_HEALING_SPELL = {
    "index": "cure-wounds",
    "name": "Cure Wounds",
    "level": 1,
    "casting_time": "1 action",
    "concentration": False,
    "duration": "Instantaneous",
    "desc": ["A creature you touch regains hit points equal to 1d8 plus your spellcasting ability modifier."],
    "heal_at_slot_level": {"1": "1d8", "2": "2d8"},
}


def test_api_healing_spell():
    spell = _api_spell_to_internal(SAMPLE_API_HEALING_SPELL)
    assert spell.resolution == "healing"
    assert spell.healing_dice == "1d8"


# ---------------------------------------------------------------------------
# Equipment converters
# ---------------------------------------------------------------------------

SAMPLE_API_WEAPON = {
    "index": "longsword",
    "name": "Longsword",
    "equipment_category": {"index": "weapon", "name": "Weapon"},
    "weapon_category": "Martial",
    "weapon_range": "Melee",
    "damage": {"damage_dice": "1d8", "damage_type": {"index": "slashing", "name": "Slashing"}},
    "properties": [{"index": "versatile", "name": "Versatile"}],
    "weight": 3,
    "range": {"normal": 5, "long": None},
}


def test_api_weapon_to_internal():
    result = _api_weapon_to_internal(SAMPLE_API_WEAPON)
    assert result["name"] == "Longsword"
    assert result["damage_dice"] == "1d8"
    assert result["damage_type"] == "slashing"
    assert "versatile" in result["properties"]


def test_api_weapon_validates_as_model():
    internal = _api_weapon_to_internal(SAMPLE_API_WEAPON)
    weapon = Weapon.model_validate(internal)
    assert weapon.name == "Longsword"


SAMPLE_API_ARMOR = {
    "index": "chain-mail",
    "name": "Chain Mail",
    "equipment_category": {"index": "armor", "name": "Armor"},
    "armor_category": "Heavy",
    "armor_class": {"base": 16, "dex_bonus": False, "max_bonus": None},
    "str_minimum": 13,
    "stealth_disadvantage": True,
    "weight": 55,
}


def test_api_armor_to_internal():
    result = _api_armor_to_internal(SAMPLE_API_ARMOR)
    assert result["name"] == "Chain Mail"
    assert result["base_ac"] == 16
    assert result["armor_type"] == "heavy"
    assert result["stealth_disadvantage"] is True
    assert result["strength_requirement"] == 13


def test_api_armor_validates_as_model():
    internal = _api_armor_to_internal(SAMPLE_API_ARMOR)
    armor = Armor.model_validate(internal)
    assert armor.name == "Chain Mail"


# ---------------------------------------------------------------------------
# Upcast diff computation
# ---------------------------------------------------------------------------

def test_compute_upcast_diff():
    assert _compute_upcast_diff("8d6", "9d6") == "+1d6 per level"
    assert _compute_upcast_diff("3d8", "5d8") == "+2d8 per level"
    assert _compute_upcast_diff("1d8", "1d8") is None


# ---------------------------------------------------------------------------
# Cache-based lookups (requires pre-populated cache from fetch_srd_data.py)
# ---------------------------------------------------------------------------

def test_monster_from_cache():
    """Goblin should be available from the API cache."""
    monster = get_monster_template("goblin")
    assert monster.name == "Goblin"
    assert monster.ac > 0
    assert monster.max_hp > 0


def test_spell_from_cache():
    """Fireball should be available from the API cache."""
    spell = get_spell("Fireball")
    assert spell is not None
    assert spell.name == "Fireball"
    assert spell.level == 3


def test_get_spell_case_insensitive():
    assert get_spell("fireball") is not None
    assert get_spell("FIREBALL") is not None


def test_unknown_monster_raises():
    with patch("src.data.srd_client._fetch_api", return_value=None):
        with pytest.raises(KeyError):
            get_monster_template("nonexistent-monster-xyz")


def test_unknown_spell_returns_none():
    with patch("src.data.srd_client._fetch_api", return_value=None):
        assert get_spell("nonexistent-spell-xyz") is None


# ---------------------------------------------------------------------------
# lookup_srd (the LLM tool)
# ---------------------------------------------------------------------------

def test_lookup_srd_monster():
    result = lookup_srd("monsters", "goblin")
    assert result["success"] is True
    assert result["name"] == "Goblin"


def test_lookup_srd_spell():
    result = lookup_srd("spells", "Fireball")
    assert result["success"] is True
    assert result["name"] == "Fireball"


def test_lookup_srd_unknown_category():
    result = lookup_srd("invalid_category", "anything")
    assert result["success"] is False
    assert "Unknown SRD category" in result["error"]
