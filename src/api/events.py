"""Bridge between EventLog entries and WebSocket event frames."""
from __future__ import annotations

from src.log.event_log import EventLog


class EventBridge:
    """Tracks new EventLog entries and converts them to WS-ready dicts."""

    def __init__(self, event_log: EventLog) -> None:
        self.event_log = event_log
        self._last_idx = len(event_log.entries)

    def drain_new_events(self) -> list[dict]:
        """Return new events since last drain as WebSocket-ready dicts."""
        entries = self.event_log.entries[self._last_idx:]
        self._last_idx = len(self.event_log.entries)
        return [
            {
                "type": "event",
                "event_type": e.tool_name,
                "data": {"inputs": e.inputs, "result": e.result, "round": e.round},
            }
            for e in entries
        ]
