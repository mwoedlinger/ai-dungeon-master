"""Spell resolution engine."""
from __future__ import annotations

import re

from src.engine.dice import roll_dice
from src.engine.rules import (
    apply_condition,
    apply_damage,
    apply_healing,
    resolve_attack,
    saving_throw,
)
from src.models.character import Character
from src.models.spells import SpellData, SpellResolution


def _apply_upcast(base_dice: str | None, spell: SpellData, cast_level: int) -> str:
    """Return damage/healing dice expression adjusted for upcast level."""
    if not base_dice:
        return "0"
    if not spell.upcast_bonus or cast_level <= spell.level:
        return base_dice
    levels_above = cast_level - spell.level
    if levels_above <= 0:
        return base_dice

    # Parse "+NdM" or "+NdM+C" from upcast_bonus
    bonus_match = re.search(r"\+(\d*d\d+)(?:\+(\d+))?", spell.upcast_bonus)
    if not bonus_match:
        return base_dice

    bonus_dice = bonus_match.group(1)
    bonus_const = int(bonus_match.group(2)) if bonus_match.group(2) else 0

    # Parse base: NdM or NdM+C
    base_match = re.fullmatch(r"(\d*)d(\d+)(?:\+(\d+))?", base_dice.strip())
    if not base_match:
        return base_dice
    base_n = int(base_match.group(1)) if base_match.group(1) else 1
    sides = int(base_match.group(2))
    base_const = int(base_match.group(3)) if base_match.group(3) else 0

    bonus_dice_match = re.fullmatch(r"(\d*)d(\d+)", bonus_dice.strip())
    if not bonus_dice_match or int(bonus_dice_match.group(2)) != sides:
        # Different die types — just append
        bonus_expr = bonus_dice + (f"+{bonus_const}" if bonus_const else "")
        return base_dice + "+" + "+".join([bonus_expr] * levels_above)

    bonus_n = int(bonus_dice_match.group(1)) if bonus_dice_match.group(1) else 1
    total_n = base_n + bonus_n * levels_above
    total_const = base_const + bonus_const * levels_above
    result = f"{total_n}d{sides}"
    if total_const:
        result += f"+{total_const}"
    return result


def _get_cantrip_dice(spell: SpellData, caster: Character) -> str:
    """Get the damage dice for a cantrip based on caster level."""
    if not spell.cantrip_scaling:
        return spell.damage_dice or "0"
    # Find the highest tier the caster qualifies for
    best_dice = spell.damage_dice or "0"
    for level_threshold in sorted(spell.cantrip_scaling.keys()):
        if caster.level >= level_threshold:
            best_dice = spell.cantrip_scaling[level_threshold]
    return best_dice


def _save_with_legendary_resistance(target: Character, ability: str, dc: int):
    """Roll a saving throw, but let monsters use legendary resistance to auto-succeed."""
    from src.models.monster import Monster
    from src.models.combat import CheckResult, DiceResult
    save = saving_throw(target, ability, dc)
    if not save.success and isinstance(target, Monster) and target.legendary_resistances_remaining > 0:
        target.legendary_resistances_remaining -= 1
        # Override to success
        return CheckResult(
            roll=save.roll,
            modifier=save.modifier,
            total=save.total,
            dc=dc,
            success=True,
            nat_20=save.nat_20,
            nat_1=save.nat_1,
        )
    return save


def resolve_spell(game_state, spell: SpellData, caster: Character, targets: list[Character], cast_level: int) -> dict:
    """Resolve a spell's mechanical effects."""
    # Validate cast level: a spell must be cast at its own level or higher
    if spell.level > 0 and cast_level < spell.level:
        return {
            "success": False,
            "error": f"{spell.name} is a level {spell.level} spell and cannot be cast "
                     f"with a level {cast_level} slot.",
        }

    # Validate spell slot
    if spell.level > 0:
        if cast_level not in caster.spell_slots or caster.spell_slots[cast_level] <= 0:
            return {
                "success": False,
                "error": f"No level {cast_level} spell slots remaining for {caster.name}.",
            }
        caster.spell_slots[cast_level] -= 1

    # Handle concentration
    dropped_concentration = None
    if spell.concentration:
        if caster.concentration:
            dropped_concentration = caster.concentration
            caster.concentration = None
        caster.concentration = spell.name

    base_result: dict = {"success": True, "spell": spell.name}
    if dropped_concentration:
        base_result["dropped_concentration"] = dropped_concentration

    match spell.resolution:
        case SpellResolution.SAVE_DAMAGE:
            dc = caster.spell_save_dc or 8
            damage_expr = _apply_upcast(spell.damage_dice, spell, cast_level)
            # AoE damage is rolled ONCE for all targets (5e RAW)
            damage_rolled = roll_dice(damage_expr).total
            results = []
            for target in targets:
                # Check legendary resistance first
                save = _save_with_legendary_resistance(target, spell.save_ability or "DEX", dc)
                damage = damage_rolled
                if save.success:
                    damage = 0 if spell.save_negates else damage // 2
                dmg_result = apply_damage(target, damage, spell.damage_type or "force")
                results.append({
                    "target": target.name,
                    "save_roll": save.total,
                    "saved": save.success,
                    "damage": dmg_result["damage_dealt"],
                    "hp_remaining": target.hp,
                })
            return {**base_result, "dc": dc, "damage_rolled": damage_rolled, "targets": results}

        case SpellResolution.ATTACK_ROLL:
            results = []
            sc_ability = caster.spellcasting_ability or "INT"
            bonus = caster.ability_scores.modifier(sc_ability) + caster.proficiency_bonus
            # Use cantrip scaling for level 0 spells
            if spell.level == 0 and spell.cantrip_scaling:
                damage_expr = _get_cantrip_dice(spell, caster)
            else:
                damage_expr = _apply_upcast(spell.damage_dice, spell, cast_level)
            damage_type = spell.damage_type or "force"
            for target in targets:
                atk = resolve_attack(
                    caster, target,
                    attack_bonus=bonus,
                    damage_dice=damage_expr,
                    damage_type=damage_type,
                )
                damage = None
                if atk.hits and atk.damage is not None:
                    dmg_result = apply_damage(target, atk.damage, damage_type)
                    damage = dmg_result["damage_dealt"]
                results.append({
                    "target": target.name,
                    "attack_total": atk.total_attack,
                    "hits": atk.hits,
                    "is_crit": atk.is_crit,
                    "damage": damage,
                    "hp_remaining": target.hp,
                })
            return {**base_result, "targets": results}

        case SpellResolution.HEALING:
            if spell.flat_healing is not None:
                # Fixed healing (e.g. Heal: 70 HP + upcast bonus)
                heal_amount = spell.flat_healing
                if spell.upcast_pattern == "flat_healing" and spell.upcast_bonus and cast_level > spell.level:
                    bonus_match = re.search(r"\+(\d+)", spell.upcast_bonus)
                    if bonus_match:
                        heal_amount += int(bonus_match.group(1)) * (cast_level - spell.level)
            else:
                heal_expr = _apply_upcast(spell.healing_dice, spell, cast_level)
                sc_ability = caster.spellcasting_ability or "WIS"
                heal_amount = roll_dice(heal_expr).total + caster.ability_scores.modifier(sc_ability)
            heal_amount = max(1, heal_amount)
            if not targets:
                return {**base_result, "error": "No target for healing spell."}
            # Roll once, apply to every target (supports Mass Cure Wounds etc.)
            target_results = []
            for t in targets:
                heal_result = apply_healing(t, heal_amount)
                target_results.append({"target": t.name, **heal_result})
            return {
                **base_result,
                "healing": heal_amount,
                "targets": target_results,
                # Legacy single-target keys (first target)
                **target_results[0],
            }

        case SpellResolution.BUFF:
            # Buffs with a mechanical condition (e.g. Shield → "shielded")
            # apply it to the targets, or the caster if none given.
            affected = []
            if spell.condition_effect:
                combat = game_state.combat if game_state.combat.active else None
                for t in (targets or [caster]):
                    apply_condition(
                        t, spell.condition_effect, spell.duration_rounds,
                        combat_state=combat,
                    )
                    affected.append(t.name)
            return {
                **base_result,
                "effect": spell.buff_effect,
                "duration_rounds": spell.duration_rounds,
                "concentration": spell.concentration,
                **({"condition_applied": spell.condition_effect, "targets": affected}
                   if affected else {}),
            }

        case SpellResolution.SAVE_EFFECT:
            dc = caster.spell_save_dc or 8
            results = []
            for target in targets:
                save = _save_with_legendary_resistance(target, spell.save_ability or "WIS", dc)
                effect_applied = not save.success
                if effect_applied and spell.condition_effect:
                    apply_condition(target, spell.condition_effect, spell.duration_rounds)
                results.append({
                    "target": target.name,
                    "save_roll": save.total,
                    "saved": save.success,
                    "effect_applied": effect_applied,
                    "condition": spell.condition_effect if effect_applied else None,
                })
            return {**base_result, "dc": dc, "targets": results}

        case SpellResolution.AUTO_DAMAGE:
            # Use cantrip scaling for level 0 spells
            if spell.level == 0 and spell.cantrip_scaling:
                damage_expr = _get_cantrip_dice(spell, caster)
            else:
                damage_expr = _apply_upcast(spell.damage_dice, spell, cast_level)
            results = []
            for target in targets:
                damage = roll_dice(damage_expr).total if damage_expr != "0" else 0
                dmg_result = apply_damage(target, damage, spell.damage_type or "force")
                results.append({
                    "target": target.name,
                    "damage": dmg_result["damage_dealt"],
                    "hp_remaining": target.hp,
                })
            return {**base_result, "targets": results}

        case SpellResolution.NARRATIVE:
            return {
                **base_result,
                "narrative_only": True,
                "description": spell.description,
            }

        case _:
            # Unknown resolution — refund the slot and restore prior concentration
            # so the failed cast has no side effects.
            if spell.level > 0:
                caster.spell_slots[cast_level] = caster.spell_slots.get(cast_level, 0) + 1
            if spell.concentration:
                caster.concentration = dropped_concentration
            return {"success": False, "error": f"Unknown spell resolution type: {spell.resolution}"}
