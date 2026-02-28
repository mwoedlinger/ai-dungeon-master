"""Context manager — assembles system prompt, manages history, compresses tokens."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.dm.backends.base import LLMBackend
    from src.campaign.campaign_db import CampaignData
    from src.engine.game_state import GameState

from src.dm.prompts import DM_ROLE_AND_RULES


class ContextManager:
    TOKEN_BUDGET_HISTORY = 80_000
    SUMMARY_TRIGGER = 60_000

    def __init__(self, campaign: "CampaignData", game_state: "GameState"):
        self.campaign = campaign
        self.game_state = game_state
        self.full_history: list[dict] = []
        self.story_summary: str = ""

    def build_system_prompt(self) -> str:
        """Flat string system prompt (used by non-Anthropic backends via _flatten_system)."""
        blocks = self.build_system_prompt_blocks()
        return "\n\n".join(b.get("text", "") for b in blocks if isinstance(b, dict))

    def build_system_prompt_blocks(self) -> list[dict]:
        """System prompt as content blocks with Anthropic prompt-caching breakpoints.

        Block 1 (cached): static rules + location context + quests.
          Invalidated only when the party changes location or completes a quest.
        Block 2 (uncached): character HP/slots/conditions + combat state + story summary.
          Changes every turn — no point caching.
        """
        stable = "\n\n".join(s for s in [
            DM_ROLE_AND_RULES,
            self._current_location_context(),
            self._active_quests_compact(),
        ] if s)

        dynamic_parts = [self._active_characters_compact()]
        if self.game_state.combat.active:
            dynamic_parts.append(self._combat_state_block())
        if self.story_summary:
            dynamic_parts.append(f"## Story So Far\n{self.story_summary}")
        dynamic = "\n\n".join(s for s in dynamic_parts if s)

        blocks: list[dict] = [
            {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
        ]
        if dynamic:
            blocks.append({"type": "text", "text": dynamic})
        return blocks

    def add_message(self, message: dict) -> None:
        self.full_history.append(message)

    def get_messages_for_api(self) -> list[dict]:
        """Return history trimmed to token budget."""
        if self._estimate_tokens() <= self.TOKEN_BUDGET_HISTORY:
            return self.full_history
        # Drop oldest messages until under budget
        trimmed = list(self.full_history)
        while len(trimmed) > 2 and self._estimate_tokens(trimmed) > self.TOKEN_BUDGET_HISTORY:
            trimmed.pop(0)
        return trimmed

    def compress_if_needed(self, backend: "LLMBackend") -> None:
        """Summarize old history if over SUMMARY_TRIGGER tokens."""
        if self._estimate_tokens() < self.SUMMARY_TRIGGER:
            return
        if len(self.full_history) < 20:
            return

        old_messages = self.full_history[:20]
        self.full_history = self.full_history[20:]

        system = (
            "Summarize the following D&D session events concisely. "
            "Focus on: key story developments, combat outcomes, "
            "NPC interactions, items gained/lost, location changes. "
            "Omit raw dice rolls and mechanical details."
        )
        messages = [{
            "role": "user",
            "content": (
                f"Previous summary:\n{self.story_summary}\n\n"
                f"New events:\n{self._format_messages(old_messages)}"
            ),
        }]
        self.story_summary = backend.compress(system=system, messages=messages)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _estimate_tokens(self, messages: list[dict] | None = None) -> int:
        msgs = messages if messages is not None else self.full_history
        return len(json.dumps(msgs)) // 4

    def _format_messages(self, messages: list[dict]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "tool_result":
                            text_parts.append(f"[tool result: {block.get('content', '')}]")
                        elif block.get("type") == "tool_use":
                            text_parts.append(f"[tool call: {block['name']}({block['input']})]")
                content = " ".join(text_parts)
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    def _current_location_context(self) -> str:
        loc_id = self.game_state.world.current_location_id
        return self.campaign.get_location_context(loc_id)

    def _active_characters_compact(self) -> str:
        lines = ["## Active Characters"]
        for char in self.game_state.player_characters:
            status = f"{char.hp}/{char.max_hp} HP"
            if char.conditions:
                status += f" [{', '.join(char.conditions)}]"
            if char.concentration:
                status += f" (concentrating: {char.concentration})"
            slots = ""
            if char.spell_slots:
                slot_str = " ".join(
                    f"L{k}:{v}/{char.max_spell_slots.get(k, v)}"
                    for k, v in sorted(char.spell_slots.items())
                )
                slots = f" | Slots: {slot_str}"
            lines.append(
                f"- **{char.name}** ({char.race} {char.class_name} {char.level}) — {status}{slots}"
            )
        return "\n".join(lines)

    def _active_quests_compact(self) -> str:
        active = [q for q in self.game_state.world.quests if q.status == "active"]
        if not active:
            return ""
        lines = ["## Active Quests"]
        for q in active:
            done = len(q.completed_objectives)
            total = len(q.objectives)
            lines.append(f"- **{q.title}**: {q.description[:100]} [{done}/{total} objectives]")
        return "\n".join(lines)

    def _combat_state_block(self) -> str:
        combat = self.game_state.combat
        lines = [
            "## COMBAT ACTIVE",
            f"Round {combat.round}",
            "Initiative order:",
        ]
        for i, cid in enumerate(combat.turn_order):
            try:
                char = self.game_state.get_character(cid)
            except KeyError:
                continue
            marker = "→ " if i == combat.current_turn_index else "  "
            c = combat.combatants[cid]
            actions = []
            if c.has_action:
                actions.append("action")
            if c.has_bonus_action:
                actions.append("bonus")
            if c.has_reaction:
                actions.append("reaction")
            action_str = ", ".join(actions) if actions else "no actions remaining"
            lines.append(
                f"{marker}{char.name} (Init {c.initiative}) — "
                f"{char.hp}/{char.max_hp} HP [{action_str}]"
            )
        return "\n".join(lines)
