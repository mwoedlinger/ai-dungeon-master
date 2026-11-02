"""Campaign time tracking engine."""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.world import TimeState

if TYPE_CHECKING:
    from src.engine.game_state import GameState


def advance_time(
    time_state: TimeState,
    hours: int = 0,
    minutes: int = 0,
    game_state: "GameState | None" = None,
) -> dict:
    """Advance the in-game clock. Returns new time and what periods elapsed.

    If *game_state* is provided, also ticks down spell/concentration durations
    for effects that operate on real-time scales (minutes, hours), and checks
    for quest deadline expirations.
    """
    old_day = time_state.day
    old_hour = time_state.hour
    was_daytime = time_state.is_daytime

    total_minutes = time_state.minute + minutes
    total_hours = time_state.hour + hours + total_minutes // 60
    time_state.minute = total_minutes % 60
    time_state.day += total_hours // 24
    time_state.hour = total_hours % 24

    days_elapsed = time_state.day - old_day
    is_daytime = time_state.is_daytime
    dawn_or_dusk = was_daytime != is_daytime

    result: dict = {
        "success": True,
        "time": time_state.formatted(),
        "day": time_state.day,
        "hour": time_state.hour,
        "minute": time_state.minute,
        "time_of_day": time_state.time_of_day,
        "is_daytime": is_daytime,
    }
    if days_elapsed > 0:
        result["days_elapsed"] = days_elapsed
    if dawn_or_dusk:
        result["transition"] = "dawn" if is_daytime else "dusk"

    # Long rest eligibility hint: 8+ hours of rest
    if hours >= 8:
        result["long_rest_eligible"] = True

    # Tick down out-of-combat spell durations (concentration + timed effects)
    if game_state is not None:
        elapsed_rounds = (hours * 60 + minutes) * 10  # 1 minute ≈ 10 rounds
        expired_effects = _tick_spell_durations(game_state, elapsed_rounds)
        if expired_effects:
            result["expired_effects"] = expired_effects

        # Check quest deadlines
        expired_quests = _check_quest_deadlines(game_state, time_state.day)
        if expired_quests:
            result["expired_quests"] = expired_quests

        # Stabilized characters regain consciousness after ~1 hour (5e: 1d4
        # hours, simplified). Without this they stay unconscious forever, and a
        # party wipe where everyone stabilizes has no way out.
        total_minutes_elapsed = hours * 60 + minutes
        revived = _wake_stable_characters(game_state, total_minutes_elapsed)
        if revived:
            result["revived"] = revived

        downed = _party_status(game_state)
        if downed["all_down"]:
            result["party_down"] = downed

    return result


def _wake_stable_characters(game_state: "GameState", elapsed_minutes: int) -> list[dict]:
    """Wake stabilized characters at 1 HP once an hour has passed."""
    if elapsed_minutes < 60 or game_state.combat.active:
        return []

    revived: list[dict] = []
    for char in game_state.characters.values():
        if "stable" not in char.conditions or "dead" in char.conditions:
            continue
        if char.hp > 0:
            continue
        char.hp = 1
        for cond in ("stable", "unconscious"):
            if cond in char.conditions:
                char.conditions.remove(cond)
        char.death_saves.successes = 0
        char.death_saves.failures = 0
        revived.append({
            "character": char.name,
            "character_id": char.id,
            "hp": char.hp,
            "note": "regained consciousness at 1 HP after resting",
        })
    return revived


def _party_status(game_state: "GameState") -> dict:
    """Summarize how much of the party is out of action."""
    pcs = game_state.player_characters
    down = [c for c in pcs if c.hp <= 0 or "dead" in c.conditions]
    dead = [c for c in down if "dead" in c.conditions]
    return {
        "all_down": bool(pcs) and len(down) == len(pcs),
        "down": [c.name for c in down],
        "dead": [c.name for c in dead],
        "note": (
            "The entire party is out of action. Narrate the aftermath — who "
            "found them, what it cost — rather than continuing as if they acted."
        ),
    }


def travel_time(
    game_state: "GameState",
    destination_id: str,
) -> dict:
    """Calculate travel time from current location to destination.

    Looks up LocationConnection for travel_hours, or falls back to defaults.
    Returns travel info including hours needed and random encounter eligibility.
    """
    current_loc_id = game_state.world.current_location_id
    current_loc = game_state.world.locations.get(current_loc_id)
    dest_loc = game_state.world.locations.get(destination_id)

    if not current_loc:
        return {"success": False, "error": f"Current location {current_loc_id!r} not found."}
    if not dest_loc:
        return {"success": False, "error": f"Destination {destination_id!r} not found."}

    # Check if locations are connected
    if destination_id not in current_loc.connected_to and not any(
        c.target_id == destination_id for c in current_loc.connections
    ):
        # Also check parent-child relationship
        if dest_loc.parent != current_loc_id and current_loc.parent != destination_id:
            return {
                "success": False,
                "error": f"{dest_loc.name} is not reachable from {current_loc.name}.",
            }

    # Look up travel time from connections list
    travel_hours = 0.0
    travel_description = ""
    for conn in current_loc.connections:
        if conn.target_id == destination_id:
            travel_hours = conn.travel_hours
            travel_description = conn.description
            break

    # If no detailed connection exists, use defaults
    if travel_hours == 0.0:
        # Parent-child = same area (instant), otherwise default 1 hour
        if dest_loc.parent == current_loc_id or current_loc.parent == destination_id:
            travel_hours = 0.0
        else:
            travel_hours = 1.0  # default for unspecified connections

    result: dict = {
        "success": True,
        "from": current_loc.name,
        "to": dest_loc.name,
        "travel_hours": travel_hours,
    }
    if travel_description:
        result["description"] = travel_description

    # Flag random encounter eligibility for overland travel
    if travel_hours >= 1.0:
        result["random_encounter_eligible"] = True
        result["note"] = "Consider rolling for a random encounter during travel."

    return result


def _tick_spell_durations(game_state: "GameState", elapsed_rounds: int) -> list[dict]:
    """Tick condition durations on all characters when time advances out of combat.

    Returns a list of expired effects for narration.
    """
    if game_state.combat.active:
        return []  # In combat, duration ticking is handled by end_turn()

    expired: list[dict] = []

    for cid, char in game_state.characters.items():
        # Concentration spells: most last up to 1 hour (600 rounds) max
        # If enough time passes, drop concentration
        if char.concentration and elapsed_rounds >= 600:
            spell_name = char.concentration
            char.concentration = None
            expired.append({
                "character": char.name,
                "effect": spell_name,
                "reason": "duration expired",
            })

    return expired


def _check_quest_deadlines(game_state: "GameState", current_day: int) -> list[dict]:
    """Check for quest deadline expirations. Auto-fail quests past their deadline."""
    expired: list[dict] = []

    for quest in game_state.world.quests:
        if quest.status != "active":
            continue
        if quest.deadline_day is not None and current_day > quest.deadline_day:
            quest.status = "failed"  # type: ignore[assignment]
            entry: dict = {
                "quest": quest.title,
                "deadline_day": quest.deadline_day,
                "current_day": current_day,
            }
            if quest.deadline_description:
                entry["deadline_description"] = quest.deadline_description
            expired.append(entry)

    return expired
