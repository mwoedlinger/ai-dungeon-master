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

# Approximate cost per million tokens by provider/model (USD)
_COST_PER_M_TOKENS: dict[str, dict[str, float]] = {
    "anthropic": {"input": 3.0, "output": 15.0},
    "deepseek": {"input": 0.27, "output": 1.10},
    "gemini": {"input": 0.075, "output": 0.30},
    "ollama": {"input": 0.0, "output": 0.0},
}


@dataclass
class SessionTokenStats:
    """Accumulated token usage for the current session."""
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_creation: int = 0
    api_calls: int = 0
    provider: str = ""

    def record(self, usage: TokenUsage) -> None:
        self.total_input += usage.input_tokens
        self.total_output += usage.output_tokens
        self.total_cache_read += usage.cache_read_tokens
        self.total_cache_creation += usage.cache_creation_tokens
        self.api_calls += 1

    @property
    def estimated_cost_usd(self) -> float:
        rates = _COST_PER_M_TOKENS.get(self.provider, {"input": 0, "output": 0})
        return (
            self.total_input * rates["input"] / 1_000_000
            + self.total_output * rates["output"] / 1_000_000
        )

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
    return any(s in msg for s in (
        "context length", "context window", "token limit",
        "max_tokens", "too many tokens", "maximum context",
        "content too large", "request too large",
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
        self.token_stats = SessionTokenStats(provider=provider)

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

            # Always use non-streaming first. This prevents the LLM's
            # intermediate reasoning (before tool calls) from leaking into
            # the player-facing narration.
            try:
                result = _call_with_retry(self.backend.complete, **api_kwargs)
            except Exception as exc:
                if _is_context_overflow(exc):
                    logger.warning("Context overflow detected, triggering emergency compression")
                    self.context_manager.compress_if_needed(self.backend, force=True)
                    try:
                        api_kwargs["messages"] = self.context_manager.get_messages_for_api(self.backend)
                        result = _call_with_retry(self.backend.complete, **api_kwargs)
                    except Exception:
                        return "[The DM's thoughts are overwhelmed — too much has happened. Please try a shorter action.]"
                else:
                    logger.error("API call failed: %s", exc)
                    return f"[The DM encounters a magical disturbance. Error: {exc}]"

            # Track token usage
            self.token_stats.record(result.usage)
            logger.debug(
                "API response: %d input tokens, %d output tokens, %d tool calls",
                result.usage.input_tokens,
                result.usage.output_tokens,
                len(result.tool_calls),
            )

            if not result.tool_calls:
                self.context_manager.add_message(result.raw_assistant_message)
                self.context_manager.compact_tool_pairs()
                self.context_manager.compress_if_needed(self.backend)
                text = result.text or "[The DM pauses thoughtfully...]"
                # Deliver final narration via callback for streaming display
                if on_text_chunk and text:
                    self._deliver_text(text, on_text_chunk)
                return text

            # Tool-call turn — dispatch all calls, loop back for narration
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

                # Debug callback for real-time display
                if self._on_tool_call:
                    self._on_tool_call(tc.name, tc.input, outcome)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "name": tc.name,       # kept for Gemini; stripped by Anthropic backend
                    "content": json.dumps(outcome),
                })

            self.context_manager.add_message({"role": "user", "content": tool_results})
            # Loop: LLM processes results and either narrates or calls more tools

        # Exceeded max iterations — force a narrative response
        logger.warning("Tool loop hit max iterations (%d)", MAX_TOOL_ITERATIONS)
        return "[The DM gathers their thoughts after a flurry of actions and prepares to continue...]"

    @staticmethod
    def _deliver_text(
        text: str,
        callback: Callable[[str], None],
        chunk_size: int = 12,
    ) -> None:
        """Deliver text to the streaming callback in small chunks."""
        for i in range(0, len(text), chunk_size):
            callback(text[i : i + chunk_size])

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
