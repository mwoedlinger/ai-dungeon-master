"""Event log for tracking mechanical events during a session."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.engine.game_state import GameState

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        game_state: "GameState | None" = None,
        persist_path: str | Path | None = None,
    ):
        self.entries: list[EventEntry] = []
        self._game_state = game_state
        self._persist_path: Path | None = None
        self._file = None

        if persist_path:
            self._persist_path = Path(persist_path)
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._file = open(self._persist_path, "a")
                logger.debug("Event log persisting to %s", self._persist_path)
            except OSError as exc:
                logger.warning("Could not open event log file %s: %s", persist_path, exc)

    def log(self, tool_name: str, inputs: dict, result: dict) -> None:
        entry = EventEntry(
            timestamp=time.time(),
            tool_name=tool_name,
            inputs=inputs,
            result=result,
            round=self._current_round(),
        )
        self.entries.append(entry)

        # Persist to JSONL file
        if self._file is not None:
            try:
                self._file.write(json.dumps(entry.model_dump(), default=str) + "\n")
                self._file.flush()
            except OSError:
                logger.warning("Failed to write event log entry", exc_info=True)

    def _current_round(self) -> int | None:
        if self._game_state and self._game_state.combat.active:
            return self._game_state.combat.round
        return None

    def get_recent(self, n: int = 10) -> list[EventEntry]:
        return self.entries[-n:]

    def get_session_recap_data(self) -> list[EventEntry]:
        """Return significant events for session recap generation."""
        return [e for e in self.entries if e.tool_name in self.SIGNIFICANT_TOOLS]

    def close(self) -> None:
        """Close the persistent log file."""
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None

    @staticmethod
    def load_entries(path: str | Path) -> list[EventEntry]:
        """Load entries from a JSONL event log file (for post-session analysis)."""
        entries = []
        path = Path(path)
        if not path.exists():
            return entries
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(EventEntry.model_validate(json.loads(line)))
                    except (json.JSONDecodeError, Exception):
                        continue
        return entries
