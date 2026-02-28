"""Rules engine — pure functions operating on model instances."""
from __future__ import annotations

from src.engine.dice import roll_dice
from src.models.character import Character, DeathSaves
from src.models.combat import AttackResult, CheckResult
from src.models.monster import Monster


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
    roll = roll_dice("1d20", advantage=advantage, disadvantage=disadvantage)
    raw = roll.kept_roll if roll.kept_roll is not None else roll.individual_rolls[0]
    modifier = char.ability_scores.modifier(ability)
    if skill and skill in char.skill_proficiencies:
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


def saving_throw(
    char: Character,
    ability: str,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
) -> CheckResult:
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
    roll = roll_dice("1d20", advantage=advantage, disadvantage=disadvantage)
    raw = roll.kept_roll if roll.kept_roll is not None else roll.individual_rolls[0]
    is_crit = raw == 20
    is_nat1 = raw == 1

    if weapon.attack_bonus_override is not None:
        attack_bonus = weapon.attack_bonus_override
        ability_mod = 0  # override means no separate ability mod
    else:
        if "finesse" in weapon.properties:
            str_mod = attacker.ability_scores.modifier("STR")
            dex_mod = attacker.ability_scores.modifier("DEX")
            ability_mod = max(str_mod, dex_mod)
        elif "ranged" in weapon.properties:
            ability_mod = attacker.ability_scores.modifier("DEX")
        else:
            ability_mod = attacker.ability_scores.modifier("STR")
        attack_bonus = ability_mod + attacker.proficiency_bonus

    hits = is_crit or (not is_nat1 and raw + attack_bonus >= target.ac)

    damage: int | None = None
    if hits:
        damage_roll = roll_dice(weapon.damage_dice)
        damage = damage_roll.total
        if is_crit:
            crit_roll = roll_dice(weapon.damage_dice)
            damage += crit_roll.total  # double dice
        damage += ability_mod  # add ability mod once

    return AttackResult(
        roll=roll,
        attack_bonus=attack_bonus,
        total_attack=raw + attack_bonus,
        target_ac=target.ac,
        hits=hits,
        is_crit=is_crit,
        is_nat1=is_nat1,
        damage=damage,
        damage_type=weapon.damage_type,
    )


def apply_damage(target: Character, amount: int, damage_type: str) -> dict:
    """Apply damage accounting for temp HP, resistances, unconsciousness."""
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
        else:
            result["dead"] = True

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


def apply_condition(target: Character, condition: str, duration_rounds: int | None = None) -> dict:
    """Apply a condition to a character."""
    if condition not in target.conditions:
        target.conditions.append(condition)
    return {"applied": condition, "target": target.name, "duration_rounds": duration_rounds}


def remove_condition(target: Character, condition: str) -> dict:
    """Remove a condition from a character."""
    if condition in target.conditions:
        target.conditions.remove(condition)
        return {"removed": condition, "target": target.name}
    return {"removed": None, "target": target.name, "note": f"{target.name} did not have condition {condition!r}"}
