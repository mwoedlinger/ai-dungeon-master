"""Character progression — spell slot tables, level-up logic, class templates."""
from __future__ import annotations

from src.engine.rules import proficiency_bonus_for_level
from src.models.character import Character

# ---------------------------------------------------------------------------
# Class features table: class → level → list of features
# ---------------------------------------------------------------------------

CLASS_FEATURES: dict[str, dict[int, list[dict]]] = {
    "Barbarian": {
        1:  [{"name": "Rage", "type": "resource", "resource": "rage", "value": 2},
             {"name": "Unarmored Defense", "type": "narrative"}],
        2:  [{"name": "Reckless Attack", "type": "narrative"},
             {"name": "Danger Sense", "type": "narrative"}],
        3:  [{"name": "Primal Path", "type": "narrative"},
             {"name": "Rage", "type": "resource", "resource": "rage", "value": 3}],
        5:  [{"name": "Extra Attack", "type": "flag", "flag": "extra_attack"},
             {"name": "Fast Movement", "type": "narrative"}],
        6:  [{"name": "Path Feature", "type": "narrative"},
             {"name": "Rage", "type": "resource", "resource": "rage", "value": 4}],
        7:  [{"name": "Feral Instinct", "type": "narrative"}],
        9:  [{"name": "Brutal Critical (1 die)", "type": "narrative"}],
        10: [{"name": "Path Feature", "type": "narrative"}],
        11: [{"name": "Relentless Rage", "type": "narrative"}],
        12: [{"name": "Rage", "type": "resource", "resource": "rage", "value": 5}],
        13: [{"name": "Brutal Critical (2 dice)", "type": "narrative"}],
        14: [{"name": "Path Feature", "type": "narrative"}],
        15: [{"name": "Persistent Rage", "type": "narrative"}],
        17: [{"name": "Brutal Critical (3 dice)", "type": "narrative"},
             {"name": "Rage", "type": "resource", "resource": "rage", "value": 6}],
        18: [{"name": "Indomitable Might", "type": "narrative"}],
        20: [{"name": "Primal Champion", "type": "narrative"},
             {"name": "Rage", "type": "resource", "resource": "rage", "value": -1}],  # unlimited
    },
    "Bard": {
        1:  [{"name": "Bardic Inspiration", "type": "scaling", "resource": "bardic_inspiration",
              "formula": "max(1, CHA_mod)"},
             {"name": "Spellcasting", "type": "narrative"}],
        2:  [{"name": "Jack of All Trades", "type": "narrative"},
             {"name": "Song of Rest", "type": "narrative"}],
        3:  [{"name": "Bard College", "type": "narrative"},
             {"name": "Expertise", "type": "narrative"}],
        5:  [{"name": "Font of Inspiration", "type": "narrative"}],
        6:  [{"name": "Countercharm", "type": "narrative"},
             {"name": "College Feature", "type": "narrative"}],
        10: [{"name": "Expertise", "type": "narrative"},
             {"name": "Magical Secrets", "type": "narrative"}],
        14: [{"name": "College Feature", "type": "narrative"},
             {"name": "Magical Secrets", "type": "narrative"}],
        18: [{"name": "Magical Secrets", "type": "narrative"}],
        20: [{"name": "Superior Inspiration", "type": "narrative"}],
    },
    "Cleric": {
        1:  [{"name": "Spellcasting", "type": "narrative"},
             {"name": "Divine Domain", "type": "narrative"}],
        2:  [{"name": "Channel Divinity", "type": "resource", "resource": "channel_divinity", "value": 1},
             {"name": "Turn Undead", "type": "narrative"}],
        5:  [{"name": "Destroy Undead (CR 1/2)", "type": "narrative"}],
        6:  [{"name": "Channel Divinity", "type": "resource", "resource": "channel_divinity", "value": 2},
             {"name": "Domain Feature", "type": "narrative"}],
        8:  [{"name": "Destroy Undead (CR 1)", "type": "narrative"},
             {"name": "Domain Feature", "type": "narrative"}],
        10: [{"name": "Divine Intervention", "type": "narrative"}],
        11: [{"name": "Destroy Undead (CR 2)", "type": "narrative"}],
        14: [{"name": "Destroy Undead (CR 3)", "type": "narrative"}],
        17: [{"name": "Destroy Undead (CR 4)", "type": "narrative"},
             {"name": "Domain Feature", "type": "narrative"}],
        18: [{"name": "Channel Divinity", "type": "resource", "resource": "channel_divinity", "value": 3}],
        20: [{"name": "Divine Intervention Improvement", "type": "narrative"}],
    },
    "Druid": {
        1:  [{"name": "Druidic", "type": "narrative"},
             {"name": "Spellcasting", "type": "narrative"}],
        2:  [{"name": "Wild Shape", "type": "resource", "resource": "wild_shape", "value": 2},
             {"name": "Druid Circle", "type": "narrative"}],
        6:  [{"name": "Circle Feature", "type": "narrative"}],
        10: [{"name": "Circle Feature", "type": "narrative"}],
        14: [{"name": "Circle Feature", "type": "narrative"}],
        18: [{"name": "Timeless Body", "type": "narrative"},
             {"name": "Beast Spells", "type": "narrative"}],
        20: [{"name": "Archdruid", "type": "narrative"}],
    },
    "Fighter": {
        1:  [{"name": "Fighting Style", "type": "narrative"},
             {"name": "Second Wind", "type": "resource", "resource": "second_wind", "value": 1}],
        2:  [{"name": "Action Surge", "type": "resource", "resource": "action_surge", "value": 1}],
        3:  [{"name": "Martial Archetype", "type": "narrative"}],
        5:  [{"name": "Extra Attack", "type": "flag", "flag": "extra_attack"}],
        7:  [{"name": "Archetype Feature", "type": "narrative"}],
        9:  [{"name": "Indomitable", "type": "resource", "resource": "indomitable", "value": 1}],
        10: [{"name": "Archetype Feature", "type": "narrative"}],
        11: [{"name": "Extra Attack (2)", "type": "narrative"}],
        13: [{"name": "Indomitable", "type": "resource", "resource": "indomitable", "value": 2}],
        15: [{"name": "Archetype Feature", "type": "narrative"}],
        17: [{"name": "Action Surge", "type": "resource", "resource": "action_surge", "value": 2},
             {"name": "Indomitable", "type": "resource", "resource": "indomitable", "value": 3}],
        18: [{"name": "Archetype Feature", "type": "narrative"}],
        20: [{"name": "Extra Attack (3)", "type": "narrative"}],
    },
    "Monk": {
        1:  [{"name": "Unarmored Defense", "type": "narrative"},
             {"name": "Martial Arts", "type": "narrative"}],
        2:  [{"name": "Ki", "type": "scaling", "resource": "ki", "formula": "level"},
             {"name": "Unarmored Movement", "type": "narrative"}],
        3:  [{"name": "Monastic Tradition", "type": "narrative"},
             {"name": "Deflect Missiles", "type": "narrative"}],
        4:  [{"name": "Slow Fall", "type": "narrative"}],
        5:  [{"name": "Extra Attack", "type": "flag", "flag": "extra_attack"},
             {"name": "Stunning Strike", "type": "narrative"}],
        6:  [{"name": "Ki-Empowered Strikes", "type": "narrative"},
             {"name": "Tradition Feature", "type": "narrative"}],
        7:  [{"name": "Evasion", "type": "flag", "flag": "evasion"},
             {"name": "Stillness of Mind", "type": "narrative"}],
        10: [{"name": "Purity of Body", "type": "narrative"}],
        11: [{"name": "Tradition Feature", "type": "narrative"}],
        13: [{"name": "Tongue of the Sun and Moon", "type": "narrative"}],
        14: [{"name": "Diamond Soul", "type": "narrative"}],
        15: [{"name": "Timeless Body", "type": "narrative"}],
        17: [{"name": "Tradition Feature", "type": "narrative"}],
        18: [{"name": "Empty Body", "type": "narrative"}],
        20: [{"name": "Perfect Self", "type": "narrative"}],
    },
    "Paladin": {
        1:  [{"name": "Divine Sense", "type": "narrative"},
             {"name": "Lay on Hands", "type": "scaling", "resource": "lay_on_hands", "formula": "level * 5"}],
        2:  [{"name": "Fighting Style", "type": "narrative"},
             {"name": "Spellcasting", "type": "narrative"},
             {"name": "Divine Smite", "type": "narrative"}],
        3:  [{"name": "Sacred Oath", "type": "narrative"},
             {"name": "Channel Divinity", "type": "resource", "resource": "channel_divinity", "value": 1}],
        5:  [{"name": "Extra Attack", "type": "flag", "flag": "extra_attack"}],
        6:  [{"name": "Aura of Protection", "type": "narrative"}],
        7:  [{"name": "Oath Feature", "type": "narrative"}],
        10: [{"name": "Aura of Courage", "type": "narrative"}],
        11: [{"name": "Improved Divine Smite", "type": "narrative"}],
        14: [{"name": "Cleansing Touch", "type": "narrative"}],
        15: [{"name": "Oath Feature", "type": "narrative"}],
        18: [{"name": "Aura Improvements", "type": "narrative"}],
        20: [{"name": "Oath Feature", "type": "narrative"}],
    },
    "Ranger": {
        1:  [{"name": "Favored Enemy", "type": "narrative"},
             {"name": "Natural Explorer", "type": "narrative"}],
        2:  [{"name": "Fighting Style", "type": "narrative"},
             {"name": "Spellcasting", "type": "narrative"}],
        3:  [{"name": "Ranger Archetype", "type": "narrative"},
             {"name": "Primeval Awareness", "type": "narrative"}],
        5:  [{"name": "Extra Attack", "type": "flag", "flag": "extra_attack"}],
        6:  [{"name": "Favored Enemy Improvement", "type": "narrative"}],
        7:  [{"name": "Archetype Feature", "type": "narrative"}],
        8:  [{"name": "Land's Stride", "type": "narrative"}],
        10: [{"name": "Hide in Plain Sight", "type": "narrative"},
             {"name": "Natural Explorer Improvement", "type": "narrative"}],
        11: [{"name": "Archetype Feature", "type": "narrative"}],
        14: [{"name": "Favored Enemy Improvement", "type": "narrative"},
             {"name": "Vanish", "type": "narrative"}],
        15: [{"name": "Archetype Feature", "type": "narrative"}],
        18: [{"name": "Feral Senses", "type": "narrative"}],
        20: [{"name": "Foe Slayer", "type": "narrative"}],
    },
    "Rogue": {
        1:  [{"name": "Sneak Attack", "type": "scaling", "resource": "sneak_attack_dice",
              "formula": "(level + 1) // 2"},
             {"name": "Thieves' Cant", "type": "narrative"},
             {"name": "Expertise", "type": "narrative"}],
        2:  [{"name": "Cunning Action", "type": "narrative"}],
        3:  [{"name": "Roguish Archetype", "type": "narrative"}],
        5:  [{"name": "Uncanny Dodge", "type": "narrative"}],
        6:  [{"name": "Expertise", "type": "narrative"}],
        7:  [{"name": "Evasion", "type": "flag", "flag": "evasion"}],
        9:  [{"name": "Archetype Feature", "type": "narrative"}],
        11: [{"name": "Reliable Talent", "type": "narrative"}],
        13: [{"name": "Archetype Feature", "type": "narrative"}],
        14: [{"name": "Blindsense", "type": "narrative"}],
        15: [{"name": "Slippery Mind", "type": "narrative"}],
        17: [{"name": "Archetype Feature", "type": "narrative"}],
        18: [{"name": "Elusive", "type": "narrative"}],
        20: [{"name": "Stroke of Luck", "type": "narrative"}],
    },
    "Sorcerer": {
        1:  [{"name": "Spellcasting", "type": "narrative"},
             {"name": "Sorcerous Origin", "type": "narrative"}],
        2:  [{"name": "Sorcery Points", "type": "scaling", "resource": "sorcery_points",
              "formula": "level"}],
        3:  [{"name": "Metamagic", "type": "narrative"}],
        6:  [{"name": "Origin Feature", "type": "narrative"}],
        10: [{"name": "Metamagic", "type": "narrative"}],
        14: [{"name": "Origin Feature", "type": "narrative"}],
        17: [{"name": "Metamagic", "type": "narrative"}],
        18: [{"name": "Origin Feature", "type": "narrative"}],
        20: [{"name": "Sorcerous Restoration", "type": "narrative"}],
    },
    "Warlock": {
        1:  [{"name": "Otherworldly Patron", "type": "narrative"},
             {"name": "Pact Magic", "type": "narrative"}],
        2:  [{"name": "Eldritch Invocations", "type": "narrative"}],
        3:  [{"name": "Pact Boon", "type": "narrative"}],
        5:  [{"name": "Eldritch Invocations", "type": "narrative"}],
        6:  [{"name": "Patron Feature", "type": "narrative"}],
        7:  [{"name": "Eldritch Invocations", "type": "narrative"}],
        9:  [{"name": "Eldritch Invocations", "type": "narrative"}],
        10: [{"name": "Patron Feature", "type": "narrative"}],
        11: [{"name": "Mystic Arcanum (6th)", "type": "narrative"}],
        12: [{"name": "Eldritch Invocations", "type": "narrative"}],
        13: [{"name": "Mystic Arcanum (7th)", "type": "narrative"}],
        14: [{"name": "Patron Feature", "type": "narrative"}],
        15: [{"name": "Mystic Arcanum (8th)", "type": "narrative"},
             {"name": "Eldritch Invocations", "type": "narrative"}],
        17: [{"name": "Mystic Arcanum (9th)", "type": "narrative"}],
        18: [{"name": "Eldritch Invocations", "type": "narrative"}],
        20: [{"name": "Eldritch Master", "type": "narrative"}],
    },
    "Wizard": {
        1:  [{"name": "Spellcasting", "type": "narrative"},
             {"name": "Arcane Recovery", "type": "narrative"}],
        2:  [{"name": "Arcane Tradition", "type": "narrative"}],
        6:  [{"name": "Tradition Feature", "type": "narrative"}],
        10: [{"name": "Tradition Feature", "type": "narrative"}],
        14: [{"name": "Tradition Feature", "type": "narrative"}],
        18: [{"name": "Spell Mastery", "type": "narrative"}],
        20: [{"name": "Signature Spells", "type": "narrative"}],
    },
}

# ---------------------------------------------------------------------------
# Spell progression
# ---------------------------------------------------------------------------

PREPARED_CASTERS = {"Cleric", "Druid", "Paladin"}
SPELLS_LEARNED_PER_LEVEL: dict[str, int] = {
    "Bard": 1, "Ranger": 1, "Sorcerer": 1, "Warlock": 1, "Wizard": 2,
}

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

    # --- Class features ---
    features_gained: list[str] = []
    for feat in CLASS_FEATURES.get(char.class_name, {}).get(new_level, []):
        if feat["type"] == "resource":
            char.class_resources[feat["resource"]] = feat["value"]
        elif feat["type"] == "flag":
            char.class_resources[feat["flag"]] = 1
        elif feat["type"] == "scaling":
            val = _eval_scaling(feat["formula"], new_level, char)
            char.class_resources[feat["resource"]] = val
        features_gained.append(feat["name"])

    # Also update scaling resources at every level (not just feature-grant levels)
    for level_feats in CLASS_FEATURES.get(char.class_name, {}).values():
        for feat in level_feats:
            if feat["type"] == "scaling" and feat["resource"] in char.class_resources:
                char.class_resources[feat["resource"]] = _eval_scaling(
                    feat["formula"], new_level, char
                )

    # --- Spell progression ---
    spell_info: dict = {}
    if new_slots:
        max_spell_level = max(new_slots.keys())
    else:
        max_spell_level = 0

    if char.class_name in PREPARED_CASTERS and max_spell_level > 0:
        spell_info["prepared_caster"] = True
        spell_info["max_spell_level"] = max_spell_level
        spell_info["note"] = f"Can now prepare spells up to level {max_spell_level}"

    if char.class_name in SPELLS_LEARNED_PER_LEVEL:
        spell_info["spells_to_learn"] = SPELLS_LEARNED_PER_LEVEL[char.class_name]
        spell_info["max_spell_level"] = max_spell_level

    return {
        "hp_gain": hp_gain,
        "new_max_hp": char.max_hp,
        "new_spell_slots": new_slots,
        "asi_available": asi,
        "features_gained": features_gained,
        "spell_progression": spell_info,
    }


def _eval_scaling(formula: str, level: int, char: Character) -> int:
    """Safely evaluate a scaling formula."""
    # Build a safe namespace with level and ability modifiers
    ns = {"level": level}
    if hasattr(char, "ability_scores"):
        for ability in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
            ns[f"{ability}_mod"] = char.ability_scores.modifier(ability)
    return int(max(1, eval(formula, {"__builtins__": {"max": max}}, ns)))  # noqa: S307


def learn_spell(char: Character, spell_name: str, max_spell_level: int) -> dict:
    """Add a spell to a character's known spells. Validates level and duplicates."""
    if spell_name in char.known_spells:
        return {"success": False, "error": f"{char.name} already knows {spell_name!r}."}
    # Import here to avoid circular imports
    from src.campaign.loader import get_spell
    spell = get_spell(spell_name)
    if spell is None:
        return {"success": False, "error": f"Spell {spell_name!r} not found in SRD data."}
    if spell.level > max_spell_level:
        return {
            "success": False,
            "error": f"{spell_name!r} is level {spell.level}, but {char.name} can only learn up to level {max_spell_level}.",
        }
    char.known_spells.append(spell_name)
    return {"success": True, "character": char.name, "spell_learned": spell_name, "spell_level": spell.level}


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

ALIGNMENTS = [
    "Lawful Good", "Neutral Good", "Chaotic Good",
    "Lawful Neutral", "True Neutral", "Chaotic Neutral",
    "Lawful Evil", "Neutral Evil", "Chaotic Evil",
]

# SRD backgrounds — skill proficiencies and starting equipment.
# Only Acolyte is in the SRD API, but these are from the Basic Rules / SRD 5.1.
BACKGROUNDS: dict[str, dict] = {
    "Acolyte": {
        "skill_proficiencies": ["Insight", "Religion"],
        "equipment": ["Holy symbol", "Prayer book", "5 sticks of incense", "Vestments", "15 gp"],
    },
    "Criminal": {
        "skill_proficiencies": ["Deception", "Stealth"],
        "equipment": ["Crowbar", "Dark common clothes with hood", "15 gp"],
    },
    "Folk Hero": {
        "skill_proficiencies": ["Animal Handling", "Survival"],
        "equipment": ["Artisan's tools", "Shovel", "Iron pot", "Common clothes", "10 gp"],
    },
    "Noble": {
        "skill_proficiencies": ["History", "Persuasion"],
        "equipment": ["Fine clothes", "Signet ring", "Scroll of pedigree", "25 gp"],
    },
    "Sage": {
        "skill_proficiencies": ["Arcana", "History"],
        "equipment": ["Bottle of ink", "Quill", "Small knife", "Letter from colleague", "Common clothes", "10 gp"],
    },
    "Soldier": {
        "skill_proficiencies": ["Athletics", "Intimidation"],
        "equipment": ["Insignia of rank", "Trophy from fallen enemy", "Dice set", "Common clothes", "10 gp"],
    },
    "Charlatan": {
        "skill_proficiencies": ["Deception", "Sleight of Hand"],
        "equipment": ["Fine clothes", "Disguise kit", "Con tools", "15 gp"],
    },
    "Entertainer": {
        "skill_proficiencies": ["Acrobatics", "Performance"],
        "equipment": ["Musical instrument", "Favor from admirer", "Costume", "15 gp"],
    },
    "Hermit": {
        "skill_proficiencies": ["Medicine", "Religion"],
        "equipment": ["Scroll case with notes", "Winter blanket", "Herbalism kit", "Common clothes", "5 gp"],
    },
    "Outlander": {
        "skill_proficiencies": ["Athletics", "Survival"],
        "equipment": ["Staff", "Hunting trap", "Trophy from animal", "Traveler's clothes", "10 gp"],
    },
    "Sailor": {
        "skill_proficiencies": ["Athletics", "Perception"],
        "equipment": ["Belaying pin (club)", "50 ft silk rope", "Lucky charm", "Common clothes", "10 gp"],
    },
    "Urchin": {
        "skill_proficiencies": ["Sleight of Hand", "Stealth"],
        "equipment": ["Small knife", "Map of home city", "Pet mouse", "Token from parents", "Common clothes", "10 gp"],
    },
}
