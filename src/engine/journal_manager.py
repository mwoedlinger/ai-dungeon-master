"""Journal manager — records events and handles background summarization."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.dm.backends.base import LLMBackend
    from src.models.journal import WorldJournal


_SUMMARY_SYSTEM = """\
You are a chronicler summarizing a D&D 5e campaign. Given the current summary \
and new events, produce an updated summary in 3-5 sentences. Focus on:
- Major story developments and decisions
- Key NPC relationships and faction shifts
- Unresolved threats and goals
Write in past tense, third person. Be concise — every word must earn its place."""

_LOCATION_SUMMARY_SYSTEM = """\
Summarize recent events at this D&D location in 2-3 sentences. Include NPC \
interactions, discoveries, and combat outcomes. Past tense, concise."""


class JournalManager:
    """Manages the world journal: recording events and background summarization.

    Summarization runs in a background thread using a separate LLM call
    (the backend's compress method, which uses a cheap model like Haiku).
    This preserves the main conversation context and doesn't block gameplay.
    """

    SUMMARY_THRESHOLD = 10  # entries before triggering re-summarization

    def __init__(self, journal: "WorldJournal", backend: "LLMBackend"):
        self.journal = journal
        self.backend = backend
        self._summary_lock = threading.Lock()
        self._pending_summary: threading.Thread | None = None

    def record_event(
        self,
        event: str,
        location_id: str = "",
        involved_npcs: list[str] | None = None,
        importance: str = "minor",
    ) -> dict:
        """Record an event and trigger background summarization if needed."""
        entry = self.journal.record_event(
            event=event,
            location_id=location_id,
            involved_npcs=involved_npcs,
            importance=importance,
        )

        # Check if we need to refresh the global summary
        if self.journal.needs_summary_refresh(self.SUMMARY_THRESHOLD):
            self._trigger_summary_refresh()

        return {
            "success": True,
            "recorded": entry.event,
            "importance": entry.importance,
            "turn": entry.turn,
        }

    def update_npc_attitude(
        self, npc_id: str, disposition: str, notes: str = ""
    ) -> dict:
        """Update NPC disposition toward the party."""
        attitude = self.journal.update_npc_attitude(npc_id, disposition, notes)
        return {
            "success": True,
            "npc_id": npc_id,
            "disposition": attitude.disposition,
            "notes": attitude.notes,
        }

    def set_world_flag(self, flag: str, value: str = "true") -> dict:
        self.journal.set_flag(flag, value)
        return {"success": True, "flag": flag, "value": value}

    def recall_events(
        self,
        query_type: str = "recent",
        query_id: str = "",
        limit: int = 10,
    ) -> dict:
        """Query the journal — used by the LLM to recall past events."""
        if query_type == "location":
            entries = self.journal.get_location_entries(query_id, limit)
        elif query_type == "npc":
            entries = self.journal.get_npc_entries(query_id, limit)
        elif query_type == "recent":
            entries = self.journal.get_recent_entries(limit)
        else:
            return {"success": False, "error": f"Unknown query_type: {query_type!r}"}

        return {
            "success": True,
            "query_type": query_type,
            "count": len(entries),
            "entries": [e.model_dump() for e in entries],
            "global_summary": self.journal.global_summary,
            "npc_attitudes": {
                npc_id: att.model_dump()
                for npc_id, att in self.journal.npc_attitudes.items()
            },
        }

    def get_context_block(self, current_location_id: str) -> str:
        """Build a context string for injection into the system prompt.

        Uses structured per-entity summaries when available.
        """
        journal = self.journal
        parts: list[str] = []

        # Global summary
        summary = journal.global_summary or journal.conversation_summary
        if summary:
            parts.append(f"## Story So Far\n{summary}")

        # Current location — summary + recent entries
        loc_summary = journal.location_summaries.get(current_location_id, "")
        loc_entries = journal.get_location_entries(current_location_id, limit=10)
        if loc_summary or loc_entries:
            lines = ["## Current Location History"]
            if loc_summary:
                lines.append(loc_summary)
            if loc_entries:
                lines.append("Recent events:")
                for e in loc_entries:
                    npcs = f" (NPCs: {', '.join(e.involved_npcs)})" if e.involved_npcs else ""
                    lines.append(f"- {e.event}{npcs}")
            parts.append("\n".join(lines))

        # NPC context
        if journal.npc_attitudes or journal.npc_summaries:
            lines = ["## NPC Knowledge"]
            for npc_id in sorted(set(journal.npc_attitudes) | set(journal.npc_summaries)):
                att = journal.npc_attitudes.get(npc_id)
                npc_sum = journal.npc_summaries.get(npc_id, "")
                att_str = f" ({att.disposition})" if att else ""
                notes_str = f" — {att.notes}" if att and att.notes else ""
                lines.append(f"- **{npc_id}**{att_str}{notes_str}")
                if npc_sum:
                    lines.append(f"  {npc_sum}")
            parts.append("\n".join(lines))

        # Faction reputations
        if journal.faction_reputations:
            lines = ["## Faction Standings"]
            for fid, rep in journal.faction_reputations.items():
                lines.append(f"- **{fid}**: {rep.score} ({rep.tier})")
                if rep.history:
                    lines.append(f"  Recent: {rep.history[-1]}")
            parts.append("\n".join(lines))

        # World flags
        if journal.world_flags:
            lines = ["## World State Flags"]
            for flag, value in journal.world_flags.items():
                lines.append(f"- {flag}: {value}")
            parts.append("\n".join(lines))

        # Recent major events
        recent_major = journal.global_entries[-5:]
        if recent_major:
            lines = ["## Recent Major Events"]
            for e in recent_major:
                lines.append(f"- {e.event}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Background summarization
    # ------------------------------------------------------------------

    def _trigger_summary_refresh(self) -> None:
        """Kick off a background thread to refresh the global summary."""
        if self._pending_summary and self._pending_summary.is_alive():
            return  # already running

        self.journal.mark_summary_refreshed()

        # Snapshot the data for the thread
        current_summary = self.journal.global_summary
        recent = self.journal.get_recent_entries(limit=20)
        event_lines = [f"- [{e.importance}] {e.event}" for e in recent]

        thread = threading.Thread(
            target=self._run_summary,
            args=(current_summary, "\n".join(event_lines)),
            daemon=True,
        )
        thread.start()
        self._pending_summary = thread

    def _run_summary(self, current_summary: str, events_text: str) -> None:
        """Run in a background thread — calls the backend to generate a summary."""
        try:
            messages = [{
                "role": "user",
                "content": (
                    f"Current summary:\n{current_summary or '(none yet)'}\n\n"
                    f"New events:\n{events_text}\n\n"
                    f"Write the updated campaign summary."
                ),
            }]
            new_summary = self.backend.compress(
                system=_SUMMARY_SYSTEM,
                messages=messages,
                max_tokens=300,
            )
            with self._summary_lock:
                self.journal.global_summary = new_summary
        except Exception:
            pass  # don't crash the game over a failed summary
