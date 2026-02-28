"""Character progression — spell slot tables, level-up logic, class templates."""
from __future__ import annotations

from src.engine.rules import proficiency_bonus_for_level
from src.models.character import Character

# ---------------------------------------------------------------------------
# Caster classification
# ---------------------------------------------------------------------------

FULL_CASTERS = {"Bard", "Cleric", "Druid", "Sorcerer", "Wizard"}
HALF_CASTERS = {"Paladin", "Ranger"}
PACT_CASTERS = {"Warlock"}

# ---------------------------------------------------------------------------
# Spell slot tables: level → {slot_tier: count}
# ---------------------------------------------------------------------------

_FULL_CASTER_SLOTS: dict[int, dict[int, int]] = {
    1:  {1: 2},
    2:  {1: 3},
    3:  {1: 4, 2: 2},
    4:  {1: 4, 2: 3},
    5:  {1: 4, 2: 3, 3: 2},
    6:  {1: 4, 2: 3, 3: 3},
    7:  {1: 4, 2: 3, 3: 3, 4: 1},
    8:  {1: 4, 2: 3, 3: 3, 4: 2},
    9:  {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    10: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
    11: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    12: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    13: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
    14: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
    15: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
    16: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
    17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1, 9: 1},
    18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 1, 7: 1, 8: 1, 9: 1},
    19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 1, 8: 1, 9: 1},
    20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1},
}

_HALF_CASTER_SLOTS: dict[int, dict[int, int]] = {
    1:  {},
    2:  {1: 2},
    3:  {1: 3},
    4:  {1: 3},
    5:  {1: 4, 2: 2},
    6:  {1: 4, 2: 2},
    7:  {1: 4, 2: 3},
    8:  {1: 4, 2: 3},
    9:  {1: 4, 2: 3, 3: 2},
    10: {1: 4, 2: 3, 3: 2},
    11: {1: 4, 2: 3, 3: 3},
    12: {1: 4, 2: 3, 3: 3},
    13: {1: 4, 2: 3, 3: 3, 4: 1},
    14: {1: 4, 2: 3, 3: 3, 4: 1},
    15: {1: 4, 2: 3, 3: 3, 4: 2},
    16: {1: 4, 2: 3, 3: 3, 4: 2},
    17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
    20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
}

# Warlock pact slots: {slot_tier: count} — all slots are one tier
_PACT_CASTER_SLOTS: dict[int, dict[int, int]] = {
    1:  {1: 1},
    2:  {1: 2},
    3:  {2: 2},
    4:  {2: 2},
    5:  {3: 2},
    6:  {3: 2},
    7:  {4: 2},
    8:  {4: 2},
    9:  {5: 2},
    10: {5: 2},
    11: {5: 3},
    12: {5: 3},
    13: {5: 3},
    14: {5: 3},
    15: {5: 3},
    16: {5: 3},
    17: {5: 4},
    18: {5: 4},
    19: {5: 4},
    20: {5: 4},
}


def get_spell_slots_for_level(class_name: str, level: int) -> dict[int, int]:
    """Return the full slot allocation {tier: count} for a class at a given level."""
    level = max(1, min(20, level))
    if class_name in FULL_CASTERS:
        return dict(_FULL_CASTER_SLOTS[level])
    if class_name in HALF_CASTERS:
        return dict(_HALF_CASTER_SLOTS[level])
    if class_name in PACT_CASTERS:
        return dict(_PACT_CASTER_SLOTS[level])
    return {}


# ---------------------------------------------------------------------------
# Level-up application
# ---------------------------------------------------------------------------

def apply_level_up(char: Character) -> dict:
    """Apply all stat changes for a level-up. char.level must already be the new level."""
    new_level = char.level

    # HP gain: floor(die/2) + 1 + CON modifier, minimum 1
    die_sides = int(char.hit_die_type[1:])  # "d10" -> 10
    con_mod = char.ability_scores.modifier("CON")
    hp_gain = max(1, (die_sides // 2 + 1) + con_mod)
    char.max_hp += hp_gain
    char.hp += hp_gain  # grant HP immediately

    # Hit dice: gain 1, capped at level
    char.hit_dice_remaining = min(char.hit_dice_remaining + 1, new_level)

    # Spell slots: add deltas from previous level to current max/remaining
    new_slots = get_spell_slots_for_level(char.class_name, new_level)
    old_slots = get_spell_slots_for_level(char.class_name, new_level - 1)
    for tier, count in new_slots.items():
        gained = count - old_slots.get(tier, 0)
        if gained > 0:
            char.max_spell_slots[tier] = count
            char.spell_slots[tier] = char.spell_slots.get(tier, 0) + gained

    # Proficiency bonus
    char.proficiency_bonus = proficiency_bonus_for_level(new_level)

    # ASI at standard levels; Fighter gets extra at 6 and 14
    standard_asi = {4, 8, 12, 16, 19}
    fighter_extra = {6, 14}
    asi = new_level in standard_asi or (char.class_name == "Fighter" and new_level in fighter_extra)

    return {
        "hp_gain": hp_gain,
        "new_max_hp": char.max_hp,
        "new_spell_slots": new_slots,
        "asi_available": asi,
    }


# ---------------------------------------------------------------------------
# Class templates for character creation
# ---------------------------------------------------------------------------

CLASS_TEMPLATES: dict[str, dict] = {
    "Barbarian": {
        "hit_die": "d12",
        "primary": ["STR", "CON", "DEX", "WIS", "CHA", "INT"],
        "saves": ["STR", "CON"],
        "armor_proficiencies": ["light", "medium", "shields"],
        "weapon_proficiencies": ["simple", "martial"],
        "skill_options": ["Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival"],
        "spellcasting_ability": None,
        "armor_type": "medium",
        "class_resources": {"rage": 2},
        "starting_weapons": [
            {"name": "Greataxe", "damage_dice": "1d12", "damage_type": "slashing", "properties": ["two-handed"]},
            {"name": "Handaxe", "damage_dice": "1d6", "damage_type": "slashing", "properties": ["light", "thrown"]},
        ],
        "starting_armor": {"name": "Hide Armor", "base_ac": 12, "armor_type": "medium"},
        "starting_spells": [],
    },
    "Bard": {
        "hit_die": "d8",
        "primary": ["CHA", "DEX", "CON", "INT", "WIS", "STR"],
        "saves": ["DEX", "CHA"],
        "armor_proficiencies": ["light"],
        "weapon_proficiencies": ["simple", "hand crossbows", "longswords", "rapiers", "shortswords"],
        "skill_options": ["Athletics", "Acrobatics", "Arcana", "History", "Insight", "Intimidation",
                          "Investigation", "Medicine", "Nature", "Perception", "Performance",
                          "Persuasion", "Religion", "Sleight of Hand", "Stealth", "Survival"],
        "spellcasting_ability": "CHA",
        "armor_type": "light",
        "class_resources": {"bardic_inspiration": 3},
        "starting_weapons": [
            {"name": "Rapier", "damage_dice": "1d8", "damage_type": "piercing", "properties": ["finesse"]},
        ],
        "starting_armor": {"name": "Leather Armor", "base_ac": 11, "armor_type": "light"},
        "starting_spells": ["Vicious Mockery", "Healing Word", "Thunderwave"],
    },
    "Cleric": {
        "hit_die": "d8",
        "primary": ["WIS", "CON", "STR", "DEX", "CHA", "INT"],
        "saves": ["WIS", "CHA"],
        "armor_proficiencies": ["light", "medium", "shields"],
        "weapon_proficiencies": ["simple"],
        "skill_options": ["History", "Insight", "Medicine", "Persuasion", "Religion"],
        "spellcasting_ability": "WIS",
        "armor_type": "medium",
        "class_resources": {"channel_divinity": 1},
        "starting_weapons": [
            {"name": "Mace", "damage_dice": "1d6", "damage_type": "bludgeoning", "properties": []},
        ],
        "starting_armor": {"name": "Chain Mail", "base_ac": 16, "armor_type": "heavy",
                           "stealth_disadvantage": True},
        "starting_spells": ["Sacred Flame", "Cure Wounds", "Guiding Bolt"],
    },
    "Druid": {
        "hit_die": "d8",
        "primary": ["WIS", "CON", "DEX", "INT", "CHA", "STR"],
        "saves": ["INT", "WIS"],
        "armor_proficiencies": ["light", "medium", "shields"],
        "weapon_proficiencies": ["clubs", "daggers", "darts", "javelins", "maces",
                                  "quarterstaffs", "scimitars", "sickles", "slings", "spears"],
        "skill_options": ["Arcana", "Animal Handling", "Insight", "Medicine", "Nature",
                          "Perception", "Religion", "Survival"],
        "spellcasting_ability": "WIS",
        "armor_type": "medium",
        "class_resources": {},
        "starting_weapons": [
            {"name": "Quarterstaff", "damage_dice": "1d6", "damage_type": "bludgeoning", "properties": ["versatile"]},
        ],
        "starting_armor": {"name": "Leather Armor", "base_ac": 11, "armor_type": "light"},
        "starting_spells": ["Shillelagh", "Healing Word", "Entangle"],
    },
    "Fighter": {
        "hit_die": "d10",
        "primary": ["STR", "CON", "DEX", "WIS", "INT", "CHA"],
        "saves": ["STR", "CON"],
        "armor_proficiencies": ["light", "medium", "heavy", "shields"],
        "weapon_proficiencies": ["simple", "martial"],
        "skill_options": ["Acrobatics", "Animal Handling", "Athletics", "History",
                          "Insight", "Intimidation", "Perception", "Survival"],
        "spellcasting_ability": None,
        "armor_type": "heavy",
        "class_resources": {"second_wind": 1},
        "starting_weapons": [
            {"name": "Longsword", "damage_dice": "1d8", "damage_type": "slashing", "properties": ["versatile"]},
        ],
        "starting_armor": {"name": "Chain Mail", "base_ac": 16, "armor_type": "heavy",
                           "stealth_disadvantage": True},
        "starting_spells": [],
    },
    "Monk": {
        "hit_die": "d8",
        "primary": ["DEX", "WIS", "CON", "STR", "INT", "CHA"],
        "saves": ["STR", "DEX"],
        "armor_proficiencies": [],
        "weapon_proficiencies": ["simple", "shortswords"],
        "skill_options": ["Acrobatics", "Athletics", "History", "Insight", "Religion", "Stealth"],
        "spellcasting_ability": None,
        "armor_type": "none",
        "class_resources": {"ki": 1},
        "starting_weapons": [
            {"name": "Shortsword", "damage_dice": "1d6", "damage_type": "piercing",
             "properties": ["finesse", "light"]},
        ],
        "starting_armor": None,
        "starting_spells": [],
    },
    "Paladin": {
        "hit_die": "d10",
        "primary": ["STR", "CHA", "CON", "WIS", "DEX", "INT"],
        "saves": ["WIS", "CHA"],
        "armor_proficiencies": ["light", "medium", "heavy", "shields"],
        "weapon_proficiencies": ["simple", "martial"],
        "skill_options": ["Athletics", "Insight", "Intimidation", "Medicine", "Persuasion", "Religion"],
        "spellcasting_ability": "CHA",
        "armor_type": "heavy",
        "class_resources": {"lay_on_hands": 5},
        "starting_weapons": [
            {"name": "Longsword", "damage_dice": "1d8", "damage_type": "slashing", "properties": ["versatile"]},
        ],
        "starting_armor": {"name": "Chain Mail", "base_ac": 16, "armor_type": "heavy",
                           "stealth_disadvantage": True},
        "starting_spells": ["Cure Wounds", "Divine Smite"],
    },
    "Ranger": {
        "hit_die": "d10",
        "primary": ["DEX", "WIS", "CON", "STR", "INT", "CHA"],
        "saves": ["STR", "DEX"],
        "armor_proficiencies": ["light", "medium", "shields"],
        "weapon_proficiencies": ["simple", "martial"],
        "skill_options": ["Animal Handling", "Athletics", "Insight", "Investigation",
                          "Nature", "Perception", "Stealth", "Survival"],
        "spellcasting_ability": "WIS",
        "armor_type": "medium",
        "class_resources": {},
        "starting_weapons": [
            {"name": "Shortbow", "damage_dice": "1d6", "damage_type": "piercing",
             "properties": ["ranged"], "range_normal": 80, "range_long": 320},
            {"name": "Shortsword", "damage_dice": "1d6", "damage_type": "piercing",
             "properties": ["finesse", "light"]},
        ],
        "starting_armor": {"name": "Scale Mail", "base_ac": 14, "armor_type": "medium",
                           "stealth_disadvantage": True},
        "starting_spells": ["Hunter's Mark", "Cure Wounds"],
    },
    "Rogue": {
        "hit_die": "d8",
        "primary": ["DEX", "INT", "CON", "WIS", "CHA", "STR"],
        "saves": ["DEX", "INT"],
        "armor_proficiencies": ["light"],
        "weapon_proficiencies": ["simple", "hand crossbows", "longswords", "rapiers", "shortswords"],
        "skill_options": ["Acrobatics", "Athletics", "Deception", "Insight", "Intimidation",
                          "Investigation", "Perception", "Performance", "Persuasion",
                          "Sleight of Hand", "Stealth"],
        "spellcasting_ability": None,
        "armor_type": "light",
        "class_resources": {},
        "starting_weapons": [
            {"name": "Rapier", "damage_dice": "1d8", "damage_type": "piercing", "properties": ["finesse"]},
            {"name": "Shortbow", "damage_dice": "1d6", "damage_type": "piercing",
             "properties": ["ranged"], "range_normal": 80, "range_long": 320},
        ],
        "starting_armor": {"name": "Leather Armor", "base_ac": 11, "armor_type": "light"},
        "starting_spells": [],
    },
    "Sorcerer": {
        "hit_die": "d6",
        "primary": ["CHA", "CON", "DEX", "WIS", "INT", "STR"],
        "saves": ["CON", "CHA"],
        "armor_proficiencies": [],
        "weapon_proficiencies": ["daggers", "darts", "slings", "quarterstaffs", "light crossbows"],
        "skill_options": ["Arcana", "Deception", "Insight", "Intimidation", "Persuasion", "Religion"],
        "spellcasting_ability": "CHA",
        "armor_type": "none",
        "class_resources": {"sorcery_points": 0},
        "starting_weapons": [
            {"name": "Quarterstaff", "damage_dice": "1d6", "damage_type": "bludgeoning", "properties": ["versatile"]},
        ],
        "starting_armor": None,
        "starting_spells": ["Fire Bolt", "Shocking Grasp", "Magic Missile", "Burning Hands"],
    },
    "Warlock": {
        "hit_die": "d8",
        "primary": ["CHA", "CON", "DEX", "WIS", "INT", "STR"],
        "saves": ["WIS", "CHA"],
        "armor_proficiencies": ["light"],
        "weapon_proficiencies": ["simple"],
        "skill_options": ["Arcana", "Deception", "History", "Intimidation", "Investigation",
                          "Nature", "Religion"],
        "spellcasting_ability": "CHA",
        "armor_type": "light",
        "class_resources": {},
        "starting_weapons": [
            {"name": "Light Crossbow", "damage_dice": "1d8", "damage_type": "piercing",
             "properties": ["ranged", "two-handed"], "range_normal": 80, "range_long": 320},
        ],
        "starting_armor": {"name": "Leather Armor", "base_ac": 11, "armor_type": "light"},
        "starting_spells": ["Eldritch Blast", "Hex", "Armor of Agathys"],
    },
    "Wizard": {
        "hit_die": "d6",
        "primary": ["INT", "CON", "DEX", "WIS", "CHA", "STR"],
        "saves": ["INT", "WIS"],
        "armor_proficiencies": [],
        "weapon_proficiencies": ["daggers", "darts", "slings", "quarterstaffs", "light crossbows"],
        "skill_options": ["Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"],
        "spellcasting_ability": "INT",
        "armor_type": "none",
        "class_resources": {},
        "starting_weapons": [
            {"name": "Quarterstaff", "damage_dice": "1d6", "damage_type": "bludgeoning", "properties": ["versatile"]},
        ],
        "starting_armor": None,
        "starting_spells": ["Fire Bolt", "Mage Hand", "Magic Missile", "Shield", "Mage Armor"],
    },
}

RACES = ["Human", "Elf", "Dwarf", "Halfling", "Half-Elf", "Half-Orc", "Gnome", "Tiefling", "Dragonborn"]
