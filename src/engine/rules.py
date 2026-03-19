"""Rules engine — pure functions operating on model instances."""
from __future__ import annotations

from src.engine.dice import roll_dice
from src.models.character import Character, DeathSaves
from src.models.combat import AttackResult, CheckResult
from src.models.monster import Monster

# ---------------------------------------------------------------------------
# Condition → mechanical effects (5e SRD)
# ---------------------------------------------------------------------------
# Each condition maps to a dict of mechanical effects:
#   attack_advantage / attack_disadvantage: bool
#   attacked_advantage / attacked_disadvantage: bool  (attackers get adv/disadv)
#   ability_check_disadvantage: bool | list[str]  (True = all, list = specific abilities)
#   saving_throw_advantage / saving_throw_disadvantage: bool | list[str]
#   speed_zero: bool
CONDITION_EFFECTS: dict[str, dict] = {
    "blinded": {
        "attack_disadvantage": True,
        "attacked_advantage": True,
        "ability_check_disadvantage": ["DEX"],  # perception-related
    },
    "charmed": {
        # Can't attack the charmer (handled narratively by LLM)
    },
    "deafened": {
        # Primarily narrative; no direct adv/disadv on attacks
    },
    "frightened": {
        "ability_check_disadvantage": True,
        "attack_disadvantage": True,
    },
    "grappled": {
        "speed_zero": True,
    },
    "incapacitated": {
        # Can't take actions or reactions (handled by action economy)
    },
    "invisible": {
        "attack_advantage": True,
        "attacked_disadvantage": True,
    },
    "paralyzed": {
        "speed_zero": True,
        "saving_throw_disadvantage": ["STR", "DEX"],
        "attacked_advantage": True,
    },
    "petrified": {
        "speed_zero": True,
        "attack_disadvantage": True,
        "saving_throw_disadvantage": ["STR", "DEX"],
        "attacked_advantage": True,
    },
    "poisoned": {
        "attack_disadvantage": True,
        "ability_check_disadvantage": True,
    },
    "prone": {
        "attack_disadvantage": True,
        "attacked_advantage": True,  # melee within 5 ft; ranged gets disadv (simplified)
    },
    "restrained": {
        "speed_zero": True,
        "attack_disadvantage": True,
        "attacked_advantage": True,
        "saving_throw_disadvantage": ["DEX"],
    },
    "stunned": {
        "speed_zero": True,
        "saving_throw_disadvantage": ["STR", "DEX"],
        "attacked_advantage": True,
    },
    "unconscious": {
        "speed_zero": True,
        "attacked_advantage": True,
        "saving_throw_disadvantage": ["STR", "DEX"],
    },
    "exhaustion_1": {
        "ability_check_disadvantage": True,
    },
    "exhaustion_2": {
        "ability_check_disadvantage": True,
        # speed halved — handled via speed_modifier if needed
    },
    "exhaustion_3": {
        "ability_check_disadvantage": True,
        "attack_disadvantage": True,
        "saving_throw_disadvantage": True,
    },
}


def _condition_modifiers(char: Character) -> dict[str, bool]:
    """Aggregate advantage/disadvantage flags from all active conditions."""
    flags: dict[str, bool] = {
        "attack_advantage": False,
        "attack_disadvantage": False,
        "attacked_advantage": False,
        "attacked_disadvantage": False,
        "ability_check_disadvantage_all": False,
        "saving_throw_disadvantage_all": False,
        "saving_throw_advantage_all": False,
    }
    for cond in char.conditions:
        effects = CONDITION_EFFECTS.get(cond, {})
        for key in ("attack_advantage", "attack_disadvantage",
                     "attacked_advantage", "attacked_disadvantage"):
            if effects.get(key):
                flags[key] = True
        ac_disadv = effects.get("ability_check_disadvantage")
        if ac_disadv is True:
            flags["ability_check_disadvantage_all"] = True
        st_disadv = effects.get("saving_throw_disadvantage")
        if st_disadv is True:
            flags["saving_throw_disadvantage_all"] = True
        st_adv = effects.get("saving_throw_advantage")
        if st_adv is True:
            flags["saving_throw_advantage_all"] = True
    return flags


def _condition_check_disadvantage(char: Character, ability: str) -> bool:
    """Check if any condition imposes disadvantage on ability checks for this ability."""
    for cond in char.conditions:
        effects = CONDITION_EFFECTS.get(cond, {})
        ac_disadv = effects.get("ability_check_disadvantage")
        if ac_disadv is True or (isinstance(ac_disadv, list) and ability in ac_disadv):
            return True
    return False


def _condition_save_disadvantage(char: Character, ability: str) -> bool:
    """Check if any condition imposes disadvantage on saving throws for this ability."""
    for cond in char.conditions:
        effects = CONDITION_EFFECTS.get(cond, {})
        st_disadv = effects.get("saving_throw_disadvantage")
        if st_disadv is True or (isinstance(st_disadv, list) and ability in st_disadv):
            return True
    return False


def proficiency_bonus_for_level(level: int) -> int:
    """Standard 5e proficiency bonus by character level."""
    if level <= 4:
        return 2
    elif level <= 8:
        return 3
    elif level <= 12:
        return 4
    elif level <= 16:
        return 5
    else:
        return 6


def xp_for_level(level: int) -> int:
    """XP required to reach the given level (standard 5e thresholds)."""
    thresholds = {
        1: 0,
        2: 300,
        3: 900,
        4: 2700,
        5: 6500,
        6: 14000,
        7: 23000,
        8: 34000,
        9: 48000,
        10: 64000,
        11: 85000,
        12: 100000,
        13: 120000,
        14: 140000,
        15: 165000,
        16: 195000,
        17: 225000,
        18: 265000,
        19: 305000,
        20: 355000,
    }
    return thresholds.get(level, 355000)


def ability_check(
    char: Character,
    ability: str,
    dc: int,
    skill: str | None = None,
    advantage: bool = False,
    disadvantage: bool = False,
) -> CheckResult:
    # Auto-apply condition-based disadvantage
    if _condition_check_disadvantage(char, ability):
        disadvantage = True
    roll = roll_dice("1d20", advantage=advantage, disadvantage=disadvantage)
    raw = roll.kept_roll if roll.kept_roll is not None else roll.individual_rolls[0]
    modifier = char.ability_scores.modifier(ability)

    is_proficient = skill is not None and skill in char.skill_proficiencies
    if is_proficient:
        # Expertise: double proficiency bonus for chosen skills (Rogue 1, Bard 3)
        if skill in getattr(char, "expertise_skills", []):
            modifier += char.proficiency_bonus * 2
        else:
            modifier += char.proficiency_bonus
    elif char.class_name == "Bard" and char.level >= 2:
        # Jack of All Trades: add half proficiency to non-proficient checks
        modifier += char.proficiency_bonus // 2

    # Reliable Talent: Rogue 11+ treats d20 < 10 as 10 for proficient checks
    if is_proficient and char.class_name == "Rogue" and char.level >= 11:
        raw = max(raw, 10)

    total = raw + modifier
    return CheckResult(
        roll=roll,
        modifier=modifier,
        total=total,
        dc=dc,
        success=total >= dc,
        nat_20=raw == 20,
        nat_1=raw == 1,
    )


def saving_throw(
    char: Character,
    ability: str,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
) -> CheckResult:
    # Auto-apply condition-based disadvantage
    if _condition_save_disadvantage(char, ability):
        disadvantage = True
    roll = roll_dice("1d20", advantage=advantage, disadvantage=disadvantage)
    raw = roll.kept_roll if roll.kept_roll is not None else roll.individual_rolls[0]
    modifier = char.ability_scores.modifier(ability)
    if ability in char.saving_throw_proficiencies:
        modifier += char.proficiency_bonus
    total = raw + modifier
    return CheckResult(
        roll=roll,
        modifier=modifier,
        total=total,
        dc=dc,
        success=total >= dc,
        nat_20=raw == 20,
        nat_1=raw == 1,
    )


def attack_roll(
    attacker: Character,
    target: Character,
    weapon,  # Weapon
    advantage: bool = False,
    disadvantage: bool = False,
) -> AttackResult:
    # Auto-apply condition-based advantage/disadvantage
    atk_flags = _condition_modifiers(attacker)
    tgt_flags = _condition_modifiers(target)
    if atk_flags["attack_advantage"]:
        advantage = True
    if atk_flags["attack_disadvantage"]:
        disadvantage = True
    if tgt_flags["attacked_advantage"]:
        advantage = True
    if tgt_flags["attacked_disadvantage"]:
        disadvantage = True

    roll = roll_dice("1d20", advantage=advantage, disadvantage=disadvantage)
    raw = roll.kept_roll if roll.kept_roll is not None else roll.individual_rolls[0]
    is_crit = raw == 20
    is_nat1 = raw == 1

    # Magic weapon bonus (from attuned items)
    magic_attack_bonus = 0
    magic_damage_bonus = 0
    for mi in getattr(attacker, "attuned_items", []):
        if mi.item_type == "weapon" and mi.name.lower() == weapon.name.lower():
            magic_attack_bonus += mi.bonus
            magic_damage_bonus += mi.bonus
            break

    if weapon.attack_bonus_override is not None:
        attack_bonus = weapon.attack_bonus_override + magic_attack_bonus
        ability_mod = 0
    else:
        if "finesse" in weapon.properties:
            str_mod = attacker.ability_scores.modifier("STR")
            dex_mod = attacker.ability_scores.modifier("DEX")
            ability_mod = max(str_mod, dex_mod)
        elif "ranged" in weapon.properties:
            ability_mod = attacker.ability_scores.modifier("DEX")
        else:
            ability_mod = attacker.ability_scores.modifier("STR")
        attack_bonus = ability_mod + attacker.proficiency_bonus + magic_attack_bonus

    # Magic armor bonus on target
    effective_ac = target.ac
    for mi in getattr(target, "attuned_items", []):
        if mi.item_type in ("armor", "shield"):
            effective_ac += mi.bonus

    hits = is_crit or (not is_nat1 and raw + attack_bonus >= effective_ac)

    damage: int | None = None
    if hits:
        damage_roll = roll_dice(weapon.damage_dice)
        damage = damage_roll.total
        if is_crit:
            crit_roll = roll_dice(weapon.damage_dice)
            damage += crit_roll.total
        damage += ability_mod + magic_damage_bonus

    return AttackResult(
        roll=roll,
        attack_bonus=attack_bonus,
        total_attack=raw + attack_bonus,
        target_ac=effective_ac,
        hits=hits,
        is_crit=is_crit,
        is_nat1=is_nat1,
        damage=damage,
        damage_type=weapon.damage_type,
    )


# ---------------------------------------------------------------------------
# Carrying capacity & encumbrance
# ---------------------------------------------------------------------------

def carrying_capacity(char: Character) -> float:
    """Max carry weight in lbs: STR × 15."""
    return char.ability_scores.STR * 15.0


def current_carry_weight(char: Character) -> float:
    """Total weight of all inventory items."""
    return sum(item.weight * item.quantity for item in char.inventory)


def encumbrance_status(char: Character) -> dict:
    """Return carry weight, capacity, and encumbrance tier.

    Variant encumbrance thresholds:
      - Normal: weight ≤ STR × 5
      - Encumbered (−10 ft speed): STR × 5 < weight ≤ STR × 10
      - Heavily encumbered (−20 ft speed, disadv on STR/DEX/CON checks): STR × 10 < weight ≤ STR × 15
      - Over capacity: weight > STR × 15 (speed 0)
    """
    weight = current_carry_weight(char)
    capacity = carrying_capacity(char)
    str_score = char.ability_scores.STR
    if weight > capacity:
        tier = "over_capacity"
        speed_penalty = char.speed  # effectively speed 0
    elif weight > str_score * 10:
        tier = "heavily_encumbered"
        speed_penalty = 20
    elif weight > str_score * 5:
        tier = "encumbered"
        speed_penalty = 10
    else:
        tier = "normal"
        speed_penalty = 0
    return {
        "current_weight": weight,
        "capacity": capacity,
        "tier": tier,
        "speed_penalty": speed_penalty,
    }


def apply_damage(target: Character, amount: int, damage_type: str) -> dict:
    """Apply damage accounting for temp HP, resistances, unconsciousness.

    HP is always clamped to 0 (no negatives). Unconscious/dead conditions
    are applied consistently regardless of the damage path.
    """
    if amount < 0:
        return {"success": False, "error": "Damage amount must be non-negative."}

    actual = amount

    if isinstance(target, Monster):
        if damage_type in target.damage_immunities:
            return {"damage_dealt": 0, "hp_remaining": target.hp, "note": f"immune to {damage_type}"}
        if damage_type in target.damage_resistances:
            actual = actual // 2

    if target.temp_hp > 0:
        absorbed = min(target.temp_hp, actual)
        target.temp_hp -= absorbed
        actual -= absorbed

    target.hp = max(0, target.hp - actual)
    result: dict = {"damage_dealt": actual, "hp_remaining": target.hp}

    if target.hp == 0:
        if target.is_player:
            if "unconscious" not in target.conditions:
                target.conditions.append("unconscious")
            result["unconscious"] = True
            if target.concentration:
                target.concentration = None
                result["concentration_broken"] = True
        else:
            if "dead" not in target.conditions:
                target.conditions.append("dead")
            result["dead"] = True
    elif target.concentration and target.is_player:
        # Auto-roll concentration save (CON save, DC = max(10, damage/2))
        con_dc = max(10, amount // 2)
        con_save = saving_throw(target, "CON", con_dc)
        result["concentration_check"] = {
            "dc": con_dc,
            "roll": con_save.total,
            "success": con_save.success,
        }
        if not con_save.success:
            result["concentration_broken"] = True
            result["concentration_dropped"] = target.concentration
            target.concentration = None

    return result


def apply_healing(target: Character, amount: int) -> dict:
    """Heal a character. Revives unconscious players."""
    was_unconscious = target.hp == 0 and "unconscious" in target.conditions
    old_hp = target.hp
    target.hp = min(target.max_hp, target.hp + amount)
    actual_healed = target.hp - old_hp
    if was_unconscious:
        if "unconscious" in target.conditions:
            target.conditions.remove("unconscious")
        target.death_saves = DeathSaves()
    return {"healed": actual_healed, "hp_now": target.hp, "revived": was_unconscious}


# ---------------------------------------------------------------------------
# Resurrection
# ---------------------------------------------------------------------------

# Resurrection spell tiers: material cost (gp), time limit description
RESURRECTION_SPELLS: dict[str, dict] = {
    "revivify": {
        "spell_level": 3,
        "material_cost": 300,
        "time_limit_description": "within 1 minute of death",
        "hp_restored": 1,
    },
    "raise_dead": {
        "spell_level": 5,
        "material_cost": 500,
        "time_limit_description": "within 10 days of death",
        "hp_restored": 1,
        "penalties": ["-4 penalty to attack rolls, saves, and ability checks (fades over 4 long rests)"],
    },
    "resurrection": {
        "spell_level": 7,
        "material_cost": 1000,
        "time_limit_description": "within 100 years of death",
        "hp_restored": "full",
    },
    "true_resurrection": {
        "spell_level": 9,
        "material_cost": 25000,
        "time_limit_description": "within 200 years of death",
        "hp_restored": "full",
    },
}


def resurrect_character(
    target: Character,
    spell_name: str,
    caster: Character | None = None,
) -> dict:
    """Resurrect a dead character using the specified spell.

    Validates that the character is dead, removes the dead/unconscious
    conditions, restores HP, and resets death saves.
    """
    if "dead" not in target.conditions:
        return {"success": False, "error": f"{target.name} is not dead."}

    spell_key = spell_name.lower().replace(" ", "_")
    spell_info = RESURRECTION_SPELLS.get(spell_key)
    if spell_info is None:
        return {
            "success": False,
            "error": f"Unknown resurrection spell: {spell_name!r}. "
                     f"Valid: {list(RESURRECTION_SPELLS.keys())}",
        }

    # Check material cost on caster
    if caster is not None:
        cost = spell_info["material_cost"]
        if caster.gold < cost:
            return {
                "success": False,
                "error": f"{caster.name} needs {cost}gp in material components but has {caster.gold}gp.",
            }
        caster.gold -= cost

    # Check spell slot on caster
    if caster is not None:
        level = spell_info["spell_level"]
        slots = caster.spell_slots.get(level, 0)
        if slots <= 0:
            return {
                "success": False,
                "error": f"{caster.name} has no level-{level} spell slots remaining.",
            }
        caster.spell_slots[level] = slots - 1

    # Perform resurrection
    target.conditions = [c for c in target.conditions if c not in ("dead", "unconscious")]
    target.death_saves = DeathSaves()

    if spell_info["hp_restored"] == "full":
        target.hp = target.max_hp
    else:
        target.hp = spell_info["hp_restored"]

    result: dict = {
        "success": True,
        "character": target.name,
        "spell": spell_name,
        "hp_restored": target.hp,
        "material_cost": spell_info["material_cost"],
    }

    if "penalties" in spell_info:
        result["penalties"] = spell_info["penalties"]
        result["note"] = (
            f"{target.name} returns to life but suffers: "
            + "; ".join(spell_info["penalties"])
        )

    return result


def apply_condition(
    target: Character,
    condition: str,
    duration_rounds: int | None = None,
    combat_state: object | None = None,
) -> dict:
    """Apply a condition to a character. Respects monster condition immunities.

    If *combat_state* is provided and has a combatant for this character,
    the duration is also recorded in condition_durations to stay in sync.
    """
    if isinstance(target, Monster) and condition in target.condition_immunities:
        return {"applied": None, "target": target.name, "note": f"immune to {condition}"}
    if condition not in target.conditions:
        target.conditions.append(condition)
    # Sync condition_durations on the combatant if in combat
    if combat_state is not None:
        combatants = getattr(combat_state, "combatants", {})
        cid = getattr(target, "id", None) or target.name
        combatant = combatants.get(cid)
        if combatant is not None:
            combatant.condition_durations[condition] = duration_rounds
    return {"applied": condition, "target": target.name, "duration_rounds": duration_rounds}


def remove_condition(
    target: Character,
    condition: str,
    combat_state: object | None = None,
) -> dict:
    """Remove a condition from a character.

    Also cleans up condition_durations on the combatant to prevent desync.
    """
    if condition in target.conditions:
        target.conditions.remove(condition)
        # Sync: remove from combatant's duration tracker too
        if combat_state is not None:
            combatants = getattr(combat_state, "combatants", {})
            cid = getattr(target, "id", None) or target.name
            combatant = combatants.get(cid)
            if combatant is not None:
                combatant.condition_durations.pop(condition, None)
        return {"removed": condition, "target": target.name}
    return {"removed": None, "target": target.name, "note": f"{target.name} did not have condition {condition!r}"}
