"""DungeonMaster — the LLM conversation loop."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from src.campaign.campaign_db import CampaignData
from src.dm.backends import create_backend
from src.dm.backends.base import TokenUsage
from src.dm.context import ContextManager
from src.dm.tools import ALL_TOOL_SCHEMAS, ToolDispatcher
from src.engine.game_state import GameState
from src.log.event_log import EventLog

logger = logging.getLogger(__name__)

# Hard cap on tool-call iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 15

# Retry settings for transient API errors
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds

# Approximate cost per million tokens (USD): (input, output, cache_read, cache_write).
# Matched by substring against the actual model name, most specific first;
# provider entries act as fallbacks when no model substring matches.
_MODEL_PRICING: list[tuple[str, tuple[float, float, float, float]]] = [
    ("claude-fable-5", (10.0, 50.0, 1.0, 12.5)),
    ("claude-opus", (5.0, 25.0, 0.50, 6.25)),
    ("claude-sonnet", (3.0, 15.0, 0.30, 3.75)),
    ("claude-haiku", (1.0, 5.0, 0.10, 1.25)),
    ("deepseek", (0.27, 1.10, 0.07, 0.27)),
    ("gemini", (0.10, 0.40, 0.025, 0.10)),
]
_PROVIDER_FALLBACK_PRICING: dict[str, tuple[float, float, float, float]] = {
    "anthropic": (3.0, 15.0, 0.30, 3.75),
    "deepseek": (0.27, 1.10, 0.07, 0.27),
    "gemini": (0.10, 0.40, 0.025, 0.10),
    "ollama": (0.0, 0.0, 0.0, 0.0),
}


def _pricing_for(provider: str, model: str) -> tuple[float, float, float, float]:
    model = (model or "").lower()
    for substring, rates in _MODEL_PRICING:
        if substring in model:
            return rates
    return _PROVIDER_FALLBACK_PRICING.get(provider, (0.0, 0.0, 0.0, 0.0))


@dataclass
class SessionTokenStats:
    """Accumulated token usage for the current session."""
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_creation: int = 0
    api_calls: int = 0
    provider: str = ""
    model: str = ""

    def record(self, usage: TokenUsage) -> None:
        self.total_input += usage.input_tokens
        self.total_output += usage.output_tokens
        self.total_cache_read += usage.cache_read_tokens
        self.total_cache_creation += usage.cache_creation_tokens
        self.api_calls += 1

    @property
    def estimated_cost_usd(self) -> float:
        in_rate, out_rate, cache_read_rate, cache_write_rate = _pricing_for(
            self.provider, self.model,
        )
        return (
            self.total_input * in_rate
            + self.total_output * out_rate
            + self.total_cache_read * cache_read_rate
            + self.total_cache_creation * cache_write_rate
        ) / 1_000_000

    def summary(self) -> dict:
        return {
            "api_calls": self.api_calls,
            "input_tokens": self.total_input,
            "output_tokens": self.total_output,
            "total_tokens": self.total_input + self.total_output,
            "cache_read_tokens": self.total_cache_read,
            "cache_creation_tokens": self.total_cache_creation,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
        }


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is a transient error worth retrying."""
    name = type(exc).__name__
    msg = str(exc).lower()
    # Rate limits, server errors, timeouts, connection errors
    if any(code in msg for code in ("429", "500", "502", "503", "529", "rate limit", "overloaded")):
        return True
    if "timeout" in name.lower() or "timeout" in msg:
        return True
    if "connection" in name.lower() or "connection" in msg:
        return True
    return False


def _is_context_overflow(exc: Exception) -> bool:
    """Check if an exception indicates the context window was exceeded."""
    msg = str(exc).lower()
    # Note: deliberately NOT matching "max_tokens" — errors about the
    # max_tokens *parameter* are validation errors, not context overflow.
    return any(s in msg for s in (
        "context length", "context window", "token limit",
        "too many tokens", "maximum context",
        "content too large", "request too large",
        "prompt is too long",
    ))


def _call_with_retry(fn: Callable, **kwargs):
    """Call *fn* with exponential backoff on transient errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(**kwargs)
        except Exception as exc:
            if _is_retryable(exc) and attempt < _MAX_RETRIES - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Transient API error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, _MAX_RETRIES, delay, exc,
                )
                time.sleep(delay)
                continue
            raise


class DungeonMaster:
    def __init__(
        self,
        game_state: GameState,
        campaign: CampaignData,
        event_log: EventLog,
        provider: str = "anthropic",
        model: str | None = None,
        save_path: str = "saves/autosave.json",
        debug: bool = False,
    ):
        self.backend = create_backend(provider, model)
        self.game_state = game_state
        self.event_log = event_log
        self.context_manager = ContextManager(campaign, game_state)
        self.tool_dispatcher = ToolDispatcher(
            game_state, event_log, save_path=save_path,
            backend=self.backend, campaign=campaign,
        )
        self.debug = debug
        self.token_stats = SessionTokenStats(
            provider=provider, model=getattr(self.backend, "model", "") or "",
        )

        # Debug callback for real-time tool call display
        self._on_tool_call: Callable[[str, dict, dict], None] | None = None

        logger.info(
            "DungeonMaster initialized: provider=%s, model=%s, debug=%s",
            provider, model or "(default)", debug,
        )

    def process_player_input(
        self,
        player_input: str,
        on_text_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """Process player input through the LLM loop, return narrative response.

        If *on_text_chunk* is provided, the final narrative is delivered via the
        callback.  All intermediate iterations (tool calls) use non-streaming
        complete so that the LLM's internal reasoning is never shown to players.
        """
        logger.debug("Player input: %s", player_input[:100])
        self.context_manager.add_message({"role": "user", "content": player_input})

        all_text_parts: list[str] = []

        for iteration in range(MAX_TOOL_ITERATIONS):
            api_kwargs = dict(
                system=self.context_manager.build_system_prompt_blocks(),
                messages=self.context_manager.get_messages_for_api(self.backend),
                tools=ALL_TOOL_SCHEMAS,
                max_tokens=2048,
            )

            logger.debug(
                "API call iteration %d: %d messages, estimated %d tokens",
                iteration,
                len(api_kwargs["messages"]),
                self.context_manager._estimate_tokens(),
            )

            if logger.isEnabledFor(logging.DEBUG):
                self._log_llm_request(api_kwargs, iteration)

            # Use streaming for all iterations — text flows to the player
            # as it generates, with natural pauses during tool resolution.
            try:
                result = _call_with_retry(
                    self.backend.stream_complete,
                    on_text_chunk=on_text_chunk,
                    **api_kwargs,
                )
            except Exception as exc:
                if _is_context_overflow(exc):
                    logger.warning("Context overflow detected, triggering emergency compression")
                    self.context_manager.compress_if_needed(self.backend, force=True)
                    try:
                        api_kwargs["messages"] = self.context_manager.get_messages_for_api(self.backend)
                        result = _call_with_retry(
                            self.backend.stream_complete,
                            on_text_chunk=on_text_chunk,
                            **api_kwargs,
                        )
                    except Exception:
                        return "[The DM's thoughts are overwhelmed — too much has happened. Please try a shorter action.]"
                else:
                    logger.error("API call failed: %s", exc)
                    return f"[The DM encounters a magical disturbance. Error: {exc}]"

            # Track token usage
            self.token_stats.record(result.usage)
            logger.debug(
                "API response: %d input tokens, %d output tokens, %d tool calls, text=%d chars",
                result.usage.input_tokens,
                result.usage.output_tokens,
                len(result.tool_calls),
                len(result.text or ""),
            )
            if logger.isEnabledFor(logging.DEBUG):
                self._log_llm_response(result, iteration)

            if result.text:
                all_text_parts.append(result.text)

            if not result.tool_calls:
                self.context_manager.add_message(result.raw_assistant_message)
                self.context_manager.compact_tool_pairs()
                self.context_manager.compress_if_needed(self.backend)
                return "\n\n".join(all_text_parts) or "[The DM pauses thoughtfully...]"

            # Tool-call turn — text was already streamed to the player
            logger.debug("Intermediate narrative (iter %d): %s", iteration, (result.text or "")[:200])
            self.context_manager.add_message(result.raw_assistant_message)

            tool_results = []
            for tc in result.tool_calls:
                logger.debug("Tool call: %s(%s)", tc.name, json.dumps(tc.input)[:200])
                outcome = self.tool_dispatcher.dispatch(tc.name, tc.input)
                logger.debug(
                    "Tool result: %s → %s",
                    tc.name,
                    json.dumps(outcome)[:200] if outcome.get("success", True)
                    else f"FAILED: {outcome.get('error', '?')}",
                )

                if self._on_tool_call:
                    self._on_tool_call(tc.name, tc.input, outcome)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "name": tc.name,
                    "content": json.dumps(outcome),
                })

            self.context_manager.add_message({"role": "user", "content": tool_results})

        logger.warning("Tool loop hit max iterations (%d)", MAX_TOOL_ITERATIONS)
        # History currently ends with a user message of tool results. Close the
        # turn with an assistant message so the next player input doesn't create
        # two consecutive user turns (which the API rejects).
        fallback = "[The DM gathers their thoughts after a flurry of actions and prepares to continue...]"
        self.context_manager.add_message({"role": "assistant", "content": fallback})
        self.context_manager.compact_tool_pairs()
        self.context_manager.compress_if_needed(self.backend)
        return "\n\n".join(all_text_parts) or fallback

    def _log_llm_request(self, api_kwargs: dict, iteration: int) -> None:
        """Log the full LLM request payload for post-session debugging."""
        system = api_kwargs.get("system", "")
        if isinstance(system, list):
            system_text = "\n\n".join(b.get("text", "") for b in system if isinstance(b, dict))
        else:
            system_text = system
        logger.debug(
            "=== LLM REQUEST (iteration %d) ===\n"
            "--- SYSTEM PROMPT (%d chars) ---\n%s\n"
            "--- MESSAGES (%d) ---\n%s\n"
            "--- TOOLS: %d schemas ---\n"
            "=== END REQUEST ===",
            iteration,
            len(system_text), system_text,
            len(api_kwargs.get("messages", [])),
            json.dumps(api_kwargs.get("messages", []), indent=2, default=str)[:50000],
            len(api_kwargs.get("tools", [])),
        )

    @staticmethod
    def _log_llm_response(result, iteration: int) -> None:
        """Log the full LLM response for post-session debugging."""
        logger.debug(
            "=== LLM RESPONSE (iteration %d) ===\n"
            "--- TEXT ---\n%s\n"
            "--- TOOL CALLS (%d) ---\n%s\n"
            "--- RAW ASSISTANT MESSAGE ---\n%s\n"
            "=== END RESPONSE ===",
            iteration,
            result.text or "(empty)",
            len(result.tool_calls),
            json.dumps(
                [{"name": tc.name, "input": tc.input} for tc in result.tool_calls],
                indent=2, default=str,
            ) if result.tool_calls else "(none)",
            json.dumps(result.raw_assistant_message, indent=2, default=str)[:20000],
        )

    def generate_story_summary(self) -> str:
        """Generate a two-section story summary: overall arc + recent events."""
        journal = self.game_state.journal

        # Gather all available context for the LLM
        parts: list[str] = []
        if journal.global_summary:
            parts.append(f"Campaign summary so far:\n{journal.global_summary}")
        if journal.conversation_summary:
            parts.append(f"Conversation summary:\n{journal.conversation_summary}")
        if journal.location_summaries:
            loc_lines = [f"  {lid}: {s}" for lid, s in journal.location_summaries.items()]
            parts.append("Location notes:\n" + "\n".join(loc_lines))
        if journal.npc_summaries:
            npc_lines = [f"  {nid}: {s}" for nid, s in journal.npc_summaries.items()]
            parts.append("NPC interactions:\n" + "\n".join(npc_lines))

        all_entries = journal.get_recent_entries(limit=30)
        if all_entries:
            entry_lines = []
            for e in all_entries:
                icon = "★" if e.importance == "major" else "·"
                loc = f" [{e.location_id}]" if e.location_id else ""
                entry_lines.append(f"  {icon} {e.event}{loc}")
            parts.append("Event log (oldest→newest):\n" + "\n".join(entry_lines))

        # Recent conversation messages (last ~10 user/assistant turns)
        recent_msgs = self.context_manager.full_history[-20:]
        convo_lines = []
        for msg in recent_msgs:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip() and role in ("user", "assistant"):
                convo_lines.append(f"  [{role}] {content[:300]}")
        if convo_lines:
            parts.append("Recent conversation:\n" + "\n".join(convo_lines))

        if not parts:
            return "The adventure has barely begun — there is little to summarize yet."

        system = (
            "You are a scribe chronicling a D&D 5e adventure. Given the campaign data below, "
            "write a story summary in two sections:\n\n"
            "## The Story So Far\n"
            "A concise overview of the entire adventure arc — who the heroes are, "
            "what they set out to do, and the major events that have shaped the story.\n\n"
            "## Recent Events\n"
            "A focused summary of what happened most recently — the last few encounters, "
            "decisions, and developments.\n\n"
            "Write in past tense, third person. Be vivid but concise (aim for ~150 words per section). "
            "Use markdown headers exactly as shown above."
        )
        messages = [{"role": "user", "content": "\n\n".join(parts) + "\n\nWrite the summary."}]
        return self.backend.compress(system=system, messages=messages, max_tokens=800)

    def generate_session_recap(self) -> str:
        """Generate a narrative recap of significant session events."""
        events = self.event_log.get_session_recap_data()
        if not events:
            return "The party's activities this session left no major marks worth chronicling."
        lines = [
            f"[Round {e.round}] {e.tool_name}: {e.inputs} -> {e.result}"
            for e in events
        ]
        system = (
            "You are a scribe chronicling a D&D 5e adventure. Given the mechanical event log below, "
            "write a vivid 2-3 paragraph narrative recap. Focus on drama, outcomes, and story "
            "significance. Past tense, third person."
        )
        messages = [
            {
                "role": "user",
                "content": "Session events:\n" + "\n".join(lines) + "\n\nWrite the recap.",
            }
        ]
        return self.backend.compress(system=system, messages=messages, max_tokens=600)
