"""Context manager — assembles system prompt, manages history, compresses tokens."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.dm.backends.base import LLMBackend
    from src.campaign.campaign_db import CampaignData
    from src.engine.game_state import GameState

logger = logging.getLogger(__name__)

from src.dm.prompts import DM_ROLE_AND_RULES


# Compression prompt — structured output with per-entity sections.
_COMPRESS_SYSTEM = """\
Summarize the following D&D session events. Organize your summary by entity \
so information is stored where it belongs. Omit raw dice rolls and mechanical details.

Output format (follow exactly, omit empty sections):

GLOBAL:
<Campaign-level summary: overarching story arc, major plot developments, party goals. \
Be concise but complete — this grows with the campaign.>

LOCATIONS:
[location_id_1]
<What happened at this location: events, discoveries, changes to the environment.>
[location_id_2]
<...>

NPCS:
[npc_id_1]
<Interaction history with this NPC: what was discussed, attitude changes, information revealed.>
[npc_id_2]
<...>

EVENTS:
- <significant event 1>
- <significant event 2>
(List 0-5 significant events as one-liners. Skip routine actions.)

Rules:
- Use the location_id and npc_id exactly as they appear in the events (lowercase, underscore-separated).
- Merge with any previous summary provided — don't repeat, update.
- If nothing happened at a location or with an NPC, omit that entry."""


@dataclass
class CompressResult:
    """Parsed output from the structured compression prompt."""
    global_summary: str = ""
    location_summaries: dict[str, str] = field(default_factory=dict)
    npc_summaries: dict[str, str] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)


def _parse_compress_output(text: str) -> CompressResult:
    """Parse the structured GLOBAL/LOCATIONS/NPCS/EVENTS format.

    Gracefully handles malformed output — if parsing fails, the entire
    text becomes the global summary.
    """
    result = CompressResult()

    # Split into sections by top-level headers
    section_pattern = re.compile(r'^(GLOBAL|LOCATIONS|NPCS|EVENTS):\s*$', re.MULTILINE)
    splits = section_pattern.split(text)

    if len(splits) < 2:
        # No recognized sections — treat entire text as global summary
        result.global_summary = text.strip()
        return result

    # splits = [preamble, "GLOBAL", content, "LOCATIONS", content, ...]
    sections: dict[str, str] = {}
    i = 1
    while i < len(splits) - 1:
        key = splits[i].strip()
        content = splits[i + 1].strip()
        sections[key] = content
        i += 2

    # Parse GLOBAL
    result.global_summary = sections.get("GLOBAL", "").strip()

    # Parse LOCATIONS — [location_id] followed by text
    loc_text = sections.get("LOCATIONS", "")
    if loc_text:
        result.location_summaries = _parse_bracketed_entries(loc_text)

    # Parse NPCS — [npc_id] followed by text
    npc_text = sections.get("NPCS", "")
    if npc_text:
        result.npc_summaries = _parse_bracketed_entries(npc_text)

    # Parse EVENTS — bullet points
    events_text = sections.get("EVENTS", "")
    for line in events_text.splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ")):
            result.events.append(line[2:].strip())

    # Fallback: if no global summary parsed but we have text, use it
    if not result.global_summary and not result.location_summaries and not result.npc_summaries:
        result.global_summary = text.strip()

    return result


def _parse_bracketed_entries(text: str) -> dict[str, str]:
    """Parse [id]\\ncontent blocks into a dict."""
    entries: dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        match = re.match(r'^\[([^\]]+)\]\s*$', line.strip())
        if match:
            if current_id is not None:
                entries[current_id] = "\n".join(current_lines).strip()
            current_id = match.group(1)
            current_lines = []
        elif current_id is not None:
            current_lines.append(line)

    if current_id is not None:
        entries[current_id] = "\n".join(current_lines).strip()

    return entries


def _compact_tool_exchange(assistant_content: list[dict], result_content: list[dict]) -> str:
    """Produce a compact one-line summary of a tool call + result pair.

    E.g. "[Engine: attack(aldric→goblin_1, longsword) → hit, 8 slashing damage]"
    """
    parts: list[str] = []
    for block in assistant_content:
        if block.get("type") != "tool_use":
            continue
        name = block["name"]
        inp = block.get("input", {})

        # Find matching result
        result_str = ""
        for rb in result_content:
            if rb.get("type") == "tool_result" and rb.get("tool_use_id") == block.get("id"):
                try:
                    result_data = json.loads(rb.get("content", "{}"))
                except (json.JSONDecodeError, TypeError):
                    result_data = {}
                result_str = _summarize_result(name, result_data)
                break

        input_str = _summarize_input(name, inp)
        parts.append(f"[Engine: {name}({input_str}) → {result_str}]")

    return " ".join(parts) if parts else "[Engine: tool call]"


def _summarize_input(name: str, inp: dict) -> str:
    """Compact representation of tool input."""
    if name in ("attack", "attack_roll"):
        attacker = inp.get("attacker_id", "?")
        target = inp.get("target_id", "?")
        weapon = inp.get("weapon_name", "")
        return f"{attacker}→{target}, {weapon}" if weapon else f"{attacker}→{target}"
    if name == "cast_spell":
        caster = inp.get("caster_id", "?")
        spell = inp.get("spell_name", "?")
        targets = inp.get("target_ids", [])
        return f"{caster} casts {spell} on {','.join(targets)}"
    if name in ("ability_check", "saving_throw"):
        char = inp.get("character_id", "?")
        ability = inp.get("ability", "?")
        skill = inp.get("skill", "")
        dc = inp.get("dc", "?")
        label = f"{skill} " if skill else ""
        return f"{char} {label}{ability} DC{dc}"
    if name == "apply_damage":
        return f"{inp.get('target_id', '?')} takes {inp.get('amount', '?')} {inp.get('damage_type', '')}"
    if name == "apply_healing":
        return f"{inp.get('target_id', '?')} healed {inp.get('amount', '?')}"
    if name in ("roll_dice",):
        return f"{inp.get('dice_expr', '?')} ({inp.get('reason', '')})"
    # Generic: just show key=value pairs compactly
    items = [f"{k}={v}" for k, v in list(inp.items())[:3]]
    return ", ".join(items)


def _summarize_result(name: str, result: dict) -> str:
    """Compact representation of tool result."""
    if not result.get("success", True):
        return f"FAILED: {result.get('error', '?')}"
    if name in ("attack", "attack_roll"):
        hit = "hit" if result.get("hits") else "miss"
        dmg = result.get("damage")
        crit = " (CRIT)" if result.get("is_crit") else ""
        return f"{hit}{crit}, {dmg} damage" if dmg else f"{hit}{crit}"
    if name == "cast_spell":
        if result.get("narrative_only"):
            return "narrative"
        targets = result.get("targets", [])
        if targets:
            parts = []
            for t in targets:
                if "damage" in t:
                    parts.append(f"{t.get('target', '?')}: {t['damage']} dmg")
                elif "saved" in t:
                    parts.append(f"{t.get('target', '?')}: {'saved' if t['saved'] else 'failed'}")
            return "; ".join(parts) if parts else "ok"
        if "healing" in result:
            return f"healed {result['healing']}"
        return "ok"
    if name in ("ability_check", "saving_throw"):
        total = result.get("total", "?")
        success = "pass" if result.get("success") else "fail"
        return f"{total} ({success})"
    if name == "roll_dice":
        return str(result.get("total", "?"))
    if name == "apply_damage":
        return f"{result.get('damage_dealt', '?')} dealt, {result.get('hp_remaining', '?')} HP left"
    if name == "apply_healing":
        return f"healed {result.get('healed', '?')}, now {result.get('hp_now', '?')} HP"
    # Generic
    return json.dumps(result)[:80]


class ContextManager:
    # Thresholds are now derived dynamically from context_window.
    # These are only fallbacks if no backend is available.
    _FALLBACK_BUDGET = 80_000
    _FALLBACK_TRIGGER = 50_000
    _MIN_MESSAGES_FOR_COMPRESS = 10

    def __init__(self, campaign: "CampaignData", game_state: "GameState"):
        self.campaign = campaign
        self.game_state = game_state
        self.full_history: list[dict] = []
        # Hydrate from persistent journal if available
        self.story_summary: str = game_state.journal.conversation_summary

    def _thresholds(self, context_window: int) -> tuple[int, int]:
        """Derive (history_budget, summary_trigger) from the model's context window.

        Reserve ~30% for system prompt + tools + response.
        Trigger compression at 75% of the history budget.
        """
        history_budget = int(context_window * 0.70)
        summary_trigger = int(history_budget * 0.75)
        return history_budget, summary_trigger

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
        # Journal context: NPC attitudes, world flags, location notes, global summary
        journal_block = self._journal_context()
        if journal_block:
            dynamic_parts.append(journal_block)
        elif self.story_summary:
            # Fallback to conversation summary if no journal entries yet
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

    def get_messages_for_api(self, backend: "LLMBackend | None" = None) -> list[dict]:
        """Return history trimmed to fit token budget.

        Performs a hard safety check: estimates total payload (system prompt +
        tools + messages) and compresses/trims to fit within the backend's
        context window, reserving space for the response.
        """
        if backend:
            budget, _ = self._thresholds(backend.context_window)
        else:
            budget = self._FALLBACK_BUDGET

        # Estimate system prompt + tools overhead (~tokens for static content)
        system_tokens = self._estimate_tokens(
            [{"content": self.build_system_prompt()}]
        )
        # Reserve space for response (max_tokens) + system prompt
        effective_budget = max(budget - system_tokens, budget // 2)

        # Compress first if over budget
        if backend and self._estimate_tokens() > effective_budget:
            self.compress_if_needed(backend, force=True)

        # If still over budget after compression, trim oldest messages
        if self._estimate_tokens() <= effective_budget:
            return self.full_history

        trimmed = list(self.full_history)
        while len(trimmed) > 2 and self._estimate_tokens(trimmed) > effective_budget:
            trimmed.pop(0)
        return trimmed

    def compact_tool_pairs(self, keep_recent: int = 2) -> None:
        """Replace resolved tool_use + tool_result pairs with compact summaries.

        A tool exchange is "resolved" when it's followed by an assistant message
        with text (the narration). The most recent `keep_recent` exchanges are
        preserved intact for immediate LLM context.
        """
        # Find resolved tool exchanges: (assistant_with_tools, user_with_results, narration)
        exchanges: list[tuple[int, int]] = []  # (assistant_idx, result_idx)
        for i in range(len(self.full_history) - 1):
            msg = self.full_history[i]
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            has_tool_use = any(b.get("type") == "tool_use" for b in content if isinstance(b, dict))
            if not has_tool_use:
                continue
            # Next message should be tool results
            if i + 1 >= len(self.full_history):
                continue
            next_msg = self.full_history[i + 1]
            next_content = next_msg.get("content")
            if not isinstance(next_content, list):
                continue
            has_results = any(b.get("type") == "tool_result" for b in next_content if isinstance(b, dict))
            if not has_results:
                continue
            # Check if there's a narration after this exchange
            if i + 2 < len(self.full_history):
                narration = self.full_history[i + 2]
                narration_content = narration.get("content")
                if narration.get("role") == "assistant" and isinstance(narration_content, str):
                    exchanges.append((i, i + 1))

        # Skip the most recent N exchanges
        if len(exchanges) <= keep_recent:
            return
        to_compact = exchanges[:-keep_recent]

        # Compact from end to preserve indices
        for asst_idx, result_idx in reversed(to_compact):
            asst_msg = self.full_history[asst_idx]
            result_msg = self.full_history[result_idx]

            asst_content = asst_msg.get("content", [])
            result_content = result_msg.get("content", [])

            # Extract any text from the assistant message (pre-tool-call narration)
            text_parts = [b["text"] for b in asst_content if isinstance(b, dict) and b.get("type") == "text"]
            compact = _compact_tool_exchange(asst_content, result_content)

            # Replace both messages with a single compact assistant message
            combined_text = " ".join(text_parts + [compact])
            self.full_history[asst_idx] = {"role": "assistant", "content": combined_text}
            self.full_history.pop(result_idx)

    def compress_if_needed(self, backend: "LLMBackend", force: bool = False) -> None:
        """Summarize old history into structured per-entity summaries.

        Produces: global campaign summary, per-location summaries, per-NPC
        summaries, and significant events. All stored persistently in the
        journal (survives save/load). Old raw entries are pruned.

        Key safety: old messages are only pruned from history *after* the
        compression API call succeeds — a failure preserves all history.
        """
        _, trigger = self._thresholds(backend.context_window)
        current_tokens = self._estimate_tokens()

        if not force and current_tokens < trigger:
            return
        if len(self.full_history) < self._MIN_MESSAGES_FOR_COMPRESS:
            return

        logger.info(
            "Compression triggered: %d estimated tokens (trigger=%d), %d messages, force=%s",
            current_tokens, trigger, len(self.full_history), force,
        )

        # Identify oldest half of messages (keep recent half for context)
        n_to_compress = max(self._MIN_MESSAGES_FOR_COMPRESS, len(self.full_history) // 2)
        old_messages = self.full_history[:n_to_compress]
        # DO NOT prune yet — only after successful compression

        journal = self.game_state.journal

        # Build context for the compression prompt: include existing summaries
        # so the LLM can merge/update them.
        prev_parts = []
        if self.story_summary:
            prev_parts.append(f"Previous global summary:\n{self.story_summary}")
        if journal.location_summaries:
            prev_parts.append("Previous location summaries:")
            for loc_id, s in journal.location_summaries.items():
                prev_parts.append(f"[{loc_id}]\n{s}")
        if journal.npc_summaries:
            prev_parts.append("Previous NPC summaries:")
            for npc_id, s in journal.npc_summaries.items():
                prev_parts.append(f"[{npc_id}]\n{s}")
        prev_context = "\n\n".join(prev_parts) if prev_parts else "(none yet)"

        messages = [{
            "role": "user",
            "content": (
                f"Existing context:\n{prev_context}\n\n"
                f"New events to integrate:\n{self._format_messages(old_messages)}"
            ),
        }]

        try:
            raw_output = backend.compress(
                system=_COMPRESS_SYSTEM, messages=messages, max_tokens=1500,
            )
        except Exception:
            logger.warning("Compression API call failed — preserving full history", exc_info=True)
            return  # History is intact; try again next cycle

        # Compression succeeded — NOW prune old messages
        tokens_before = self._estimate_tokens()
        self.full_history = self.full_history[n_to_compress:]
        tokens_after = self._estimate_tokens()

        parsed = _parse_compress_output(raw_output)

        logger.info(
            "Compression complete: %d messages compressed, %d→%d estimated tokens (freed ~%d), "
            "%d location summaries, %d NPC summaries, %d events extracted",
            n_to_compress,
            tokens_before, tokens_after, tokens_before - tokens_after,
            len(parsed.location_summaries),
            len(parsed.npc_summaries),
            len(parsed.events),
        )
        if parsed.global_summary:
            logger.debug("Compressed global summary: %s", parsed.global_summary[:200])

        # Update global summary
        if parsed.global_summary:
            self.story_summary = parsed.global_summary
            journal.conversation_summary = parsed.global_summary

        # Update per-location summaries (merge with existing)
        for loc_id, summary in parsed.location_summaries.items():
            journal.location_summaries[loc_id] = summary

        # Update per-NPC summaries (merge with existing)
        for npc_id, summary in parsed.npc_summaries.items():
            journal.npc_summaries[npc_id] = summary

        # Record significant events
        loc_id = self.game_state.world.current_location_id
        for event_text in parsed.events:
            journal.record_event(
                event=event_text,
                location_id=loc_id,
                importance="major",
            )

        # Prune old raw entries now that they're captured in summaries
        journal.prune_summarized_entries()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _estimate_tokens(self, messages: list[dict] | None = None) -> int:
        """Estimate token count from serialized message size.

        Uses ~3 chars/token which better matches typical LLM tokenization
        for mixed English text + JSON structure (conservative vs. old //4).
        """
        msgs = messages if messages is not None else self.full_history
        return len(json.dumps(msgs)) // 3

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

    def _journal_context(self) -> str:
        """Build journal context block for the system prompt.

        Uses structured per-entity summaries when available, falling back
        to raw entries. Only current-location and present-NPC details are
        injected; other locations/NPCs are available via recall_events tool.
        """
        journal = self.game_state.journal
        loc_id = self.game_state.world.current_location_id
        parts: list[str] = []

        # Global campaign arc
        summary = journal.global_summary or journal.conversation_summary
        if summary:
            parts.append(f"## Story So Far\n{summary}")

        # Current location — summary + recent raw entries
        loc_summary = journal.location_summaries.get(loc_id, "")
        loc_entries = journal.get_location_entries(loc_id, limit=10)
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

        # NPC context — attitudes + summaries for NPCs at current location
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

        # World flags
        if journal.world_flags:
            lines = ["## World State Flags"]
            for flag, value in journal.world_flags.items():
                lines.append(f"- {flag}: {value}")
            parts.append("\n".join(lines))

        # Recent major events (global, not location-specific)
        recent_major = journal.global_entries[-5:]
        if recent_major:
            lines = ["## Recent Major Events"]
            for e in recent_major:
                lines.append(f"- {e.event}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def _current_location_context(self) -> str:
        loc_id = self.game_state.world.current_location_id
        return self.campaign.get_location_context(loc_id, token_budget=1500)

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
            header = f"{char.race} {char.class_name} {char.level}"
            if char.background:
                header += f", {char.background}"
            if char.alignment:
                header += f", {char.alignment}"
            lines.append(f"- **{char.name}** ({header}) — {status}{slots}")
            # Personality context for roleplay guidance
            personality_parts = []
            if char.personality_traits:
                personality_parts.append(f"Traits: {char.personality_traits}")
            if char.ideals:
                personality_parts.append(f"Ideals: {char.ideals}")
            if char.bonds:
                personality_parts.append(f"Bonds: {char.bonds}")
            if char.flaws:
                personality_parts.append(f"Flaws: {char.flaws}")
            if personality_parts:
                lines.append(f"  *{'; '.join(personality_parts)}*")
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
            "Initiative order (dead/defeated combatants omitted):",
        ]
        for i, cid in enumerate(combat.turn_order):
            try:
                char = self.game_state.get_character(cid)
            except KeyError:
                continue
            # Omit dead combatants — their turns are auto-skipped
            if char.hp <= 0 or "dead" in char.conditions:
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
                f"{marker}{char.name} [{cid}] (Init {c.initiative}) — "
                f"{char.hp}/{char.max_hp} HP [{action_str}]"
            )
        return "\n".join(lines)
