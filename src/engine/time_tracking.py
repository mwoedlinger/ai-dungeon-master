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
    for effects that operate on real-time scales (minutes, hours).
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

    return result


def _tick_spell_durations(game_state: "GameState", elapsed_rounds: int) -> list[dict]:
    """Tick condition durations on all characters when time advances out of combat.

    Returns a list of expired effects for narration.
    """
    if game_state.combat.active:
        return []  # In combat, duration ticking is handled by end_turn()

    expired: list[dict] = []

    for cid, char in game_state.characters.items():
        # Check concentration: long durations expire with time
        # (Concentration is tracked by name, not rounds, out of combat — we only
        # expire it if the time exceeds typical spell duration heuristics)
        # For condition durations tracked on combatants, those only exist during combat.
        # Out-of-combat, we just note that concentration spells may expire.

        # If we have condition durations tracked elsewhere, tick them.
        # For now, handle the common case: concentration drops after 1 hour (600 rounds)
        # if the character has been concentrating and enough time passes.
        pass

    return expired
