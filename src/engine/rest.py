"""Rest mechanics — short and long rests."""
from __future__ import annotations

from src.engine.dice import roll_dice
from src.models.character import Character, DeathSaves


def short_rest(character: Character, hit_dice_to_spend: int) -> dict:
    """Spend hit dice to recover HP. Restores short-rest class resources."""
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

    result: dict = {
        "success": True,
        "healed": character.hp - old_hp,
        "rolls": rolls,
        "hp_now": character.hp,
        "hit_dice_remaining": character.hit_dice_remaining,
    }

    # Restore short-rest class resources
    restored = _restore_short_rest_resources(character)
    if restored:
        result["resources_restored"] = restored

    # Warlock pact slots restore on short rest
    if character.class_name == "Warlock" and character.max_spell_slots:
        character.spell_slots = dict(character.max_spell_slots)
        result["spell_slots_restored"] = True
        result["spell_slots"] = dict(character.spell_slots)

    return result


def _restore_short_rest_resources(character: Character) -> dict[str, int]:
    """Restore class resources that recharge on short rest."""
    from src.engine.progression import SHORT_REST_RESOURCES, get_max_class_resources

    max_resources = get_max_class_resources(character)
    restored: dict[str, int] = {}
    for resource in SHORT_REST_RESOURCES:
        if resource in max_resources:
            old = character.class_resources.get(resource, 0)
            new_val = max_resources[resource]
            if new_val > old:
                character.class_resources[resource] = new_val
                restored[resource] = new_val

    # Bardic Inspiration restores on short rest at Bard 5+ (Font of Inspiration)
    if character.class_name == "Bard" and character.level >= 5:
        if "bardic_inspiration" in max_resources:
            old = character.class_resources.get("bardic_inspiration", 0)
            new_val = max_resources["bardic_inspiration"]
            if new_val > old:
                character.class_resources["bardic_inspiration"] = new_val
                restored["bardic_inspiration"] = new_val

    return restored


def long_rest(character: Character) -> dict:
    """Full HP recovery, reset spell slots, restore all class resources, recover half hit dice."""
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

    # Restore ALL class resources to max
    restored = _restore_all_resources(character)

    result: dict = {
        "success": True,
        "hp": character.hp,
        "spell_slots_restored": bool(character.max_spell_slots),
        "spell_slots": dict(character.spell_slots),
        "hit_dice_recovered": recovered_dice,
        "hit_dice_remaining": character.hit_dice_remaining,
    }
    if restored:
        result["resources_restored"] = restored
    return result


def _restore_all_resources(character: Character) -> dict[str, int]:
    """Restore all class resources to their maximum values (long rest)."""
    from src.engine.progression import get_max_class_resources

    max_resources = get_max_class_resources(character)
    restored: dict[str, int] = {}
    for resource, max_val in max_resources.items():
        old = character.class_resources.get(resource, 0)
        if max_val != old:
            character.class_resources[resource] = max_val
            restored[resource] = max_val
    return restored
