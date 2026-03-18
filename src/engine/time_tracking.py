"""Campaign time tracking engine."""
from __future__ import annotations

from src.models.world import TimeState


def advance_time(time_state: TimeState, hours: int = 0, minutes: int = 0) -> dict:
    """Advance the in-game clock. Returns new time and what periods elapsed."""
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

    return result
