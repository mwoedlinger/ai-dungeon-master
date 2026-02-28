"""Event log for tracking mechanical events during a session."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.engine.game_state import GameState


class EventEntry(BaseModel):
    timestamp: float
    tool_name: str
    inputs: dict
    result: dict
    round: int | None = None


class EventLog:
    SIGNIFICANT_TOOLS = frozenset({
        "attack", "cast_spell", "apply_damage", "apply_healing",
        "end_combat", "award_xp", "set_location", "update_quest",
        "death_save", "start_combat",
    })

    def __init__(self, game_state: "GameState | None" = None):
        self.entries: list[EventEntry] = []
        self._game_state = game_state

    def log(self, tool_name: str, inputs: dict, result: dict) -> None:
        self.entries.append(
            EventEntry(
                timestamp=time.time(),
                tool_name=tool_name,
                inputs=inputs,
                result=result,
                round=self._current_round(),
            )
        )

    def _current_round(self) -> int | None:
        if self._game_state and self._game_state.combat.active:
            return self._game_state.combat.round
        return None

    def get_recent(self, n: int = 10) -> list[EventEntry]:
        return self.entries[-n:]

    def get_session_recap_data(self) -> list[EventEntry]:
        """Return significant events for session recap generation."""
        return [e for e in self.entries if e.tool_name in self.SIGNIFICANT_TOOLS]
