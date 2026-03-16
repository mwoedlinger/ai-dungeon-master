"""World journal models — persistent memory of what happened during play."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class NpcAttitude(BaseModel):
    """Tracks how an NPC feels about the party, overriding campaign defaults."""
    disposition: Literal["friendly", "neutral", "hostile", "fearful"] = "neutral"
    notes: str = ""  # e.g. "Party helped rescue her son", "Intimidated into cooperation"


class JournalEntry(BaseModel):
    """A single recorded event — one-line summary of something significant."""
    event: str  # concise summary: "Elder Mora revealed her son is cursed"
    location_id: str = ""
    involved_npcs: list[str] = []
    importance: Literal["major", "minor"] = "minor"
    turn: int = 0  # rough ordering


class WorldJournal(BaseModel):
    """Hierarchical persistent memory for the campaign."""

    # --- Global layer: big-picture story beats ---
    global_summary: str = ""  # LLM-generated rolling summary of the campaign arc
    global_entries: list[JournalEntry] = []  # major events only

    # --- Location layer: detailed per-location notes ---
    location_entries: dict[str, list[JournalEntry]] = {}  # location_id -> entries

    # --- NPC attitudes ---
    npc_attitudes: dict[str, NpcAttitude] = {}  # npc_id -> attitude

    # --- World flags for branching state ---
    world_flags: dict[str, str] = {}  # e.g. {"bridge_destroyed": "true"}

    # --- Internal bookkeeping ---
    turn_counter: int = 0
    _entries_since_summary: int = 0  # not persisted, reset on load

    def record_event(
        self,
        event: str,
        location_id: str = "",
        involved_npcs: list[str] | None = None,
        importance: str = "minor",
    ) -> JournalEntry:
        """Record a new event, filing it in the appropriate layer."""
        self.turn_counter += 1
        entry = JournalEntry(
            event=event,
            location_id=location_id,
            involved_npcs=involved_npcs or [],
            importance=importance,  # type: ignore[arg-type]
            turn=self.turn_counter,
        )

        if importance == "major":
            self.global_entries.append(entry)

        if location_id:
            self.location_entries.setdefault(location_id, []).append(entry)

        self._entries_since_summary += 1
        return entry

    def update_npc_attitude(
        self, npc_id: str, disposition: str, notes: str = ""
    ) -> NpcAttitude:
        """Update an NPC's attitude toward the party."""
        existing = self.npc_attitudes.get(npc_id, NpcAttitude())
        existing.disposition = disposition  # type: ignore[assignment]
        if notes:
            if existing.notes:
                existing.notes += f"; {notes}"
            else:
                existing.notes = notes
        self.npc_attitudes[npc_id] = existing
        return existing

    def set_flag(self, flag: str, value: str = "true") -> None:
        self.world_flags[flag] = value

    def get_flag(self, flag: str) -> str | None:
        return self.world_flags.get(flag)

    def needs_summary_refresh(self, threshold: int = 10) -> bool:
        """Whether enough new entries have accumulated to warrant re-summarization."""
        return self._entries_since_summary >= threshold

    def mark_summary_refreshed(self) -> None:
        self._entries_since_summary = 0

    # --- Query helpers ---

    def get_location_entries(self, location_id: str, limit: int = 20) -> list[JournalEntry]:
        """Get the most recent entries for a specific location."""
        entries = self.location_entries.get(location_id, [])
        return entries[-limit:]

    def get_npc_entries(self, npc_id: str, limit: int = 10) -> list[JournalEntry]:
        """Get entries involving a specific NPC (across all locations)."""
        results = []
        for entries in self.location_entries.values():
            for e in entries:
                if npc_id in e.involved_npcs:
                    results.append(e)
        for e in self.global_entries:
            if npc_id in e.involved_npcs and e not in results:
                results.append(e)
        results.sort(key=lambda e: e.turn)
        return results[-limit:]

    def get_recent_entries(self, limit: int = 10) -> list[JournalEntry]:
        """Get the most recent entries across all locations."""
        all_entries: list[JournalEntry] = list(self.global_entries)
        for entries in self.location_entries.values():
            all_entries.extend(entries)
        # Deduplicate (major events appear in both global + location)
        seen: set[int] = set()
        unique: list[JournalEntry] = []
        for e in all_entries:
            eid = id(e)
            if eid not in seen:
                seen.add(eid)
                unique.append(e)
        unique.sort(key=lambda e: e.turn)
        return unique[-limit:]
