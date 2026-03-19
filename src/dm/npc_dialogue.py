"""NPC dialogue sub-agent — separate LLM call per NPC with tailored system prompt."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.campaign.campaign_db import CampaignData, NPCProfile
    from src.dm.backends.base import LLMBackend
    from src.models.journal import WorldJournal


class NPCDialogueSession:
    """Ephemeral dialogue session for one NPC within one scene."""

    MAX_TURNS = 6

    def __init__(
        self,
        npc: "NPCProfile",
        backend: "LLMBackend",
        campaign: "CampaignData",
        journal: "WorldJournal | None" = None,
    ):
        self.npc = npc
        self.backend = backend
        self.history: list[dict] = []
        self.turn_count = 0
        self._system_prompt = self._build_npc_prompt(npc, campaign, journal)

    def respond(self, player_input: str, context: str = "") -> str:
        """Get NPC response to player input."""
        if self.turn_count >= self.MAX_TURNS:
            return (
                f"[{self.npc.name} seems to have said all they want to say for now. "
                "The conversation winds down naturally.]"
            )

        user_msg = player_input
        if context:
            user_msg = f"[DM context: {context}]\n\nPlayer says: {player_input}"

        self.history.append({"role": "user", "content": user_msg})

        response = self.backend.complete(
            system=self._system_prompt,
            messages=self.history,
            tools=[],
            max_tokens=512,
        )

        self.history.append({"role": "assistant", "content": response.text})
        self.turn_count += 1
        return response.text

    def summarize(self) -> str:
        """Brief summary of the conversation for the main DM's context."""
        if not self.history:
            return f"No conversation with {self.npc.name}."
        system = (
            "Summarize this NPC conversation in 1-2 sentences. "
            "Focus on what information was exchanged and any promises made."
        )
        messages = [{"role": "user", "content": self._format_history()}]
        return self.backend.compress(system=system, messages=messages, max_tokens=200)

    def _format_history(self) -> str:
        parts = []
        for msg in self.history:
            role = "Player" if msg["role"] == "user" else self.npc.name
            parts.append(f"{role}: {msg['content']}")
        return "\n".join(parts)

    @staticmethod
    def _build_npc_prompt(
        npc: "NPCProfile",
        campaign: "CampaignData",
        journal: "WorldJournal | None" = None,
    ) -> str:
        """Build information-gated prompt for the NPC, including prior interaction history."""
        lines = [
            f"You are {npc.name}, an NPC in a D&D 5e campaign.",
            f"Setting: {campaign.title} — {campaign.setting_overview[:200]}",
            "",
            "## Your Character",
            f"**Personality:** {npc.personality}",
            f"**Goals:** {npc.goals}",
            f"**Disposition toward the party:** {npc.disposition}",
            "",
            "## Roleplaying Guidelines",
            "- Stay completely in character. Never break the fourth wall.",
            "- Speak naturally with contractions, fragments, and emotion appropriate to your personality.",
            "- React to the player's tone — if they're threatening, show fear or defiance as fits your character.",
            "- You can share what you know freely (your personality, goals, common knowledge).",
        ]

        # Inject prior interaction history from journal
        if journal is not None:
            npc_id = npc.id or npc.name.lower().replace(" ", "_")
            # Check for attitude changes
            attitude = journal.npc_attitudes.get(npc_id)
            if attitude and attitude.notes:
                lines.extend([
                    "",
                    "## Your Current Feelings About the Party",
                    f"**Disposition:** {attitude.disposition}",
                    f"**Why:** {attitude.notes}",
                ])
            # Inject NPC summary if available
            npc_summary = journal.npc_summaries.get(npc_id, "")
            if npc_summary:
                lines.extend([
                    "",
                    "## Prior Interactions with This Party",
                    npc_summary,
                ])
            # Inject recent journal entries involving this NPC
            entries = journal.get_npc_entries(npc_id, limit=10)
            if entries:
                lines.extend([
                    "",
                    "## Recent Events Involving You",
                    "These events happened recently — you remember them:",
                ])
                for e in entries:
                    lines.append(f"- {e.event}")

        if npc.secret:
            lines.extend([
                "",
                "## Secret (HIDDEN — do NOT reveal unless compelled)",
                f"You are hiding: {npc.secret}",
                "- Do NOT volunteer this information.",
                "- If pressured (e.g., 'DM context' mentions a successful Intimidation or high Persuasion check), "
                "you may hint at or reluctantly reveal parts of it.",
                "- If the DM context mentions a failed check, deflect or lie.",
            ])

        lines.extend([
            "",
            "## Important",
            "- Keep responses to 2-4 sentences. This is dialogue, not monologue.",
            "- If asked about things you wouldn't know, say so in character.",
            "- Never reference game mechanics (AC, HP, spell slots, etc.).",
        ])

        return "\n".join(lines)
