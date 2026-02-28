"""Rest mechanics — short and long rests."""
from __future__ import annotations

from src.engine.dice import roll_dice
from src.models.character import Character, DeathSaves


def short_rest(character: Character, hit_dice_to_spend: int) -> dict:
    """Spend hit dice to recover HP."""
    if hit_dice_to_spend > character.hit_dice_remaining:
        return {
            "success": False,
            "error": f"Only {character.hit_dice_remaining} hit dice remaining for {character.name}.",
        }

    total_healed = 0
    rolls = []
    for _ in range(hit_dice_to_spend):
        roll = roll_dice(character.hit_die_type)
        con_mod = character.ability_scores.modifier("CON")
        heal = max(1, roll.total + con_mod)
        total_healed += heal
        rolls.append({"roll": roll.total, "con_mod": con_mod, "total": heal})
        character.hit_dice_remaining -= 1

    old_hp = character.hp
    character.hp = min(character.max_hp, character.hp + total_healed)
    return {
        "success": True,
        "healed": character.hp - old_hp,
        "rolls": rolls,
        "hp_now": character.hp,
        "hit_dice_remaining": character.hit_dice_remaining,
    }


def long_rest(character: Character) -> dict:
    """Full HP recovery, reset spell slots, recover half hit dice."""
    character.hp = character.max_hp
    character.spell_slots = dict(character.max_spell_slots)
    recovered_dice = max(1, character.level // 2)
    character.hit_dice_remaining = min(
        character.level,
        character.hit_dice_remaining + recovered_dice,
    )
    # Only persistent conditions (like curses) survive a long rest
    character.conditions = [c for c in character.conditions if c in ("cursed",)]
    character.death_saves = DeathSaves()
    character.concentration = None
    return {
        "success": True,
        "hp": character.hp,
        "spell_slots_restored": bool(character.max_spell_slots),
        "spell_slots": dict(character.spell_slots),
        "hit_dice_recovered": recovered_dice,
        "hit_dice_remaining": character.hit_dice_remaining,
    }
