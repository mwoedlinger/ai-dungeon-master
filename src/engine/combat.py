"""Combat engine — initiative, turn management, death saves, XP."""
from __future__ import annotations

from src.engine.dice import roll_dice
from src.engine.progression import apply_level_up
from src.engine.rules import xp_for_level
from src.models.combat import Combatant, CombatState


def start_combat(game_state, participant_ids: list[str]) -> dict:
    """Roll initiative for all participants and create CombatState."""
    initiatives: list[tuple[str, int]] = []

    for cid in participant_ids:
        char = game_state.get_character(cid)
        roll = roll_dice("1d20")
        raw = roll.individual_rolls[0]
        init = raw + char.ability_scores.modifier("DEX")
        initiatives.append((cid, init))

    # Sort descending; ties broken by DEX modifier then name (deterministic)
    initiatives.sort(key=lambda x: (x[1], game_state.get_character(x[0]).ability_scores.modifier("DEX")), reverse=True)

    combatants = {}
    for cid, init in initiatives:
        char = game_state.get_character(cid)
        combatants[cid] = Combatant(
            character_id=cid,
            initiative=init,
            movement_remaining=char.speed,
        )

    game_state.combat = CombatState(
        active=True,
        round=1,
        turn_order=[cid for cid, _ in initiatives],
        current_turn_index=0,
        combatants=combatants,
    )

    turn_order_info = [
        {"id": cid, "name": game_state.get_character(cid).name, "initiative": init}
        for cid, init in initiatives
    ]
    return {
        "success": True,
        "turn_order": turn_order_info,
        "round": 1,
        "first_up": game_state.get_character(initiatives[0][0]).name,
    }


def end_turn(game_state) -> dict:
    """Advance to next combatant. Tick conditions, reset actions."""
    combat = game_state.combat
    if not combat.active:
        return {"success": False, "error": "No active combat."}

    # Tick condition durations for the character whose turn just ended
    current_id = combat.current_combatant_id
    current_combatant = combat.combatants[current_id]
    current_char = game_state.get_character(current_id)

    expired = []
    for condition, duration in list(current_combatant.condition_durations.items()):
        if duration is not None:
            if duration <= 1:
                expired.append(condition)
                del current_combatant.condition_durations[condition]
            else:
                current_combatant.condition_durations[condition] = duration - 1

    for cond in expired:
        if cond in current_char.conditions:
            current_char.conditions.remove(cond)

    # Advance turn, skipping dead combatants (0 HP)
    n = len(combat.turn_order)
    next_index = (combat.current_turn_index + 1) % n
    new_round = combat.round
    if next_index == 0:
        new_round += 1

    # Skip combatants that are dead (0 HP or have "dead" condition)
    skipped = 0
    while skipped < n:
        cid = combat.turn_order[next_index]
        char = game_state.get_character(cid)
        if char.hp > 0 and "dead" not in char.conditions:
            break
        next_index = (next_index + 1) % n
        if next_index == 0:
            new_round += 1
        skipped += 1

    combat.current_turn_index = next_index
    combat.round = new_round

    # Reset actions for the next combatant
    next_id = combat.turn_order[next_index]
    next_char = game_state.get_character(next_id)
    combat.combatants[next_id].has_action = True
    combat.combatants[next_id].has_bonus_action = True
    combat.combatants[next_id].has_reaction = True
    combat.combatants[next_id].movement_remaining = next_char.speed

    return {
        "success": True,
        "next_up": next_char.name,
        "round": new_round,
        "expired_conditions": expired,
    }


def end_combat(game_state, xp_awarded: int) -> dict:
    """End combat, distribute XP, check for level-ups."""
    game_state.combat = CombatState()  # reset to inactive state

    # Remove monsters from characters dict
    monster_ids = [
        cid for cid in list(game_state.characters.keys())
        if cid not in game_state.player_character_ids
    ]
    for mid in monster_ids:
        del game_state.characters[mid]

    # Award XP
    pc_ids = game_state.player_character_ids
    if not pc_ids:
        return {"success": True, "xp_awarded": 0, "level_ups": []}

    xp_each = xp_awarded // len(pc_ids)
    level_ups = []

    for cid in pc_ids:
        char = game_state.characters.get(cid)
        if not char:
            continue
        char.xp += xp_each
        while char.level < 20 and char.xp >= xp_for_level(char.level + 1):
            char.level += 1
            details = apply_level_up(char)
            level_ups.append({"character": char.name, "new_level": char.level, **details})

    return {
        "success": True,
        "xp_awarded": xp_awarded,
        "xp_each": xp_each,
        "level_ups": level_ups,
    }


def death_save(game_state, character_id: str) -> dict:
    """Roll a death saving throw for an unconscious character."""
    char = game_state.get_character(character_id)
    if "unconscious" not in char.conditions:
        return {"success": False, "error": f"{char.name} is not unconscious."}

    roll = roll_dice("1d20")
    value = roll.individual_rolls[0]

    result: dict = {"roll": value}

    if value == 1:
        char.death_saves.failures += 2
        result["outcome"] = "critical_failure"
        result["failures"] = char.death_saves.failures
    elif value == 20:
        char.hp = 1
        char.conditions.remove("unconscious")
        char.death_saves = type(char.death_saves)()  # reset
        result["outcome"] = "miraculous_recovery"
        result["hp_now"] = 1
    elif value >= 10:
        char.death_saves.successes += 1
        result["outcome"] = "success"
        result["successes"] = char.death_saves.successes
    else:
        char.death_saves.failures += 1
        result["outcome"] = "failure"
        result["failures"] = char.death_saves.failures

    if char.death_saves.successes >= 3:
        char.conditions.remove("unconscious")
        char.death_saves.successes = 3  # cap
        result["stabilized"] = True
    elif char.death_saves.failures >= 3:
        char.conditions.append("dead")
        if "unconscious" in char.conditions:
            char.conditions.remove("unconscious")
        result["dead"] = True

    result["success"] = True
    return result
