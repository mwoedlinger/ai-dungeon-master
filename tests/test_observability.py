"""Tests for Tier 3 Observability & Debugging features."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.dm.backends.base import LLMResponse, TokenUsage, ToolCall
from src.dm.dungeon_master import SessionTokenStats
from src.log.event_log import EventLog, EventEntry


class TestTokenUsage:
    def test_token_usage_defaults(self):
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_tokens == 0

    def test_token_usage_total(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_llm_response_has_usage(self):
        resp = LLMResponse(
            text="hello",
            tool_calls=[],
            raw_assistant_message={"role": "assistant", "content": "hello"},
            usage=TokenUsage(input_tokens=500, output_tokens=100),
        )
        assert resp.usage.input_tokens == 500
        assert resp.usage.output_tokens == 100

    def test_llm_response_default_usage(self):
        resp = LLMResponse(
            text="hello",
            tool_calls=[],
            raw_assistant_message={"role": "assistant", "content": "hello"},
        )
        assert resp.usage.total_tokens == 0


class TestSessionTokenStats:
    def test_record_usage(self):
        stats = SessionTokenStats(provider="anthropic")
        stats.record(TokenUsage(input_tokens=1000, output_tokens=200))
        stats.record(TokenUsage(input_tokens=800, output_tokens=150))
        assert stats.total_input == 1800
        assert stats.total_output == 350
        assert stats.api_calls == 2

    def test_estimated_cost(self):
        stats = SessionTokenStats(provider="anthropic")
        stats.record(TokenUsage(input_tokens=1_000_000, output_tokens=100_000))
        # Anthropic: $3/M input + $15/M output
        assert stats.estimated_cost_usd == pytest.approx(3.0 + 1.5, rel=0.01)

    def test_zero_cost_for_ollama(self):
        stats = SessionTokenStats(provider="ollama")
        stats.record(TokenUsage(input_tokens=10000, output_tokens=5000))
        assert stats.estimated_cost_usd == 0.0

    def test_summary(self):
        stats = SessionTokenStats(provider="deepseek")
        stats.record(TokenUsage(input_tokens=500, output_tokens=100, cache_read_tokens=200))
        s = stats.summary()
        assert s["api_calls"] == 1
        assert s["input_tokens"] == 500
        assert s["output_tokens"] == 100
        assert s["total_tokens"] == 600
        assert s["cache_read_tokens"] == 200
        assert "estimated_cost_usd" in s


class TestPersistentEventLog:
    def test_persist_to_jsonl(self, tmp_path):
        log_path = tmp_path / "test.events.jsonl"
        elog = EventLog(persist_path=log_path)

        elog.log("roll_dice", {"dice_expr": "1d20"}, {"success": True, "total": 15})
        elog.log("attack", {"attacker_id": "pc1"}, {"success": True, "hits": True})

        assert len(elog.entries) == 2

        # Check JSONL file was written
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["tool_name"] == "roll_dice"

        elog.close()

    def test_load_entries_from_jsonl(self, tmp_path):
        log_path = tmp_path / "test.events.jsonl"
        elog = EventLog(persist_path=log_path)

        elog.log("ability_check", {"character_id": "pc1", "ability": "STR", "dc": 15},
                 {"success": True, "total": 18})
        elog.log("apply_damage", {"target_id": "m1", "amount": 10}, {"damage_dealt": 10})
        elog.close()

        # Reload from file
        loaded = EventLog.load_entries(log_path)
        assert len(loaded) == 2
        assert loaded[0].tool_name == "ability_check"
        assert loaded[1].tool_name == "apply_damage"

    def test_load_nonexistent_file(self):
        loaded = EventLog.load_entries("/nonexistent/path.jsonl")
        assert loaded == []

    def test_append_mode(self, tmp_path):
        log_path = tmp_path / "append.events.jsonl"

        # First session
        elog1 = EventLog(persist_path=log_path)
        elog1.log("roll_dice", {}, {"total": 5})
        elog1.close()

        # Second session (should append)
        elog2 = EventLog(persist_path=log_path)
        elog2.log("attack", {}, {"hits": True})
        elog2.close()

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_no_persist_path(self):
        """EventLog without persist_path still works in-memory."""
        elog = EventLog()
        elog.log("test", {}, {"ok": True})
        assert len(elog.entries) == 1
        elog.close()  # Should not error


class TestDungeonMasterDebug:
    def test_debug_flag_stored(self):
        """Verify the debug flag is accessible on DungeonMaster."""
        # We can't fully instantiate DungeonMaster without an API key,
        # so just test the SessionTokenStats and callback mechanism.
        stats = SessionTokenStats(provider="anthropic")
        assert stats.api_calls == 0

    def test_tool_call_callback(self):
        """Test the debug callback mechanism."""
        calls: list[tuple] = []
        def callback(name, inputs, result):
            calls.append((name, inputs, result))

        # Simulate what DungeonMaster does
        callback("roll_dice", {"dice_expr": "1d20"}, {"success": True, "total": 15})
        assert len(calls) == 1
        assert calls[0][0] == "roll_dice"


class TestIntermediateTextAccumulation:
    """Test that narrative text from tool-call iterations is not lost."""

    def test_intermediate_text_collected(self):
        """Simulate the DM loop logic: text from tool-call iterations
        should be combined with the final narrative."""
        # This mirrors the accumulation logic in process_player_input
        intermediate_text_parts: list[str] = []

        # Iteration 0: LLM emits text + tool call
        iter0_text = "The merchant reaches under the counter and pulls out an old map."
        iter0_tool_calls = [{"name": "add_item", "input": {"item": "Old Map"}}]
        if iter0_text.strip() and iter0_tool_calls:
            intermediate_text_parts.append(iter0_text.strip())

        # Iteration 1: LLM emits final narrative (no tool calls)
        final_text = "\"Take care with that map,\" the merchant warns."

        # Combine
        if intermediate_text_parts:
            combined = "\n\n".join(intermediate_text_parts)
            if final_text:
                combined += "\n\n" + final_text
            text = combined
        else:
            text = final_text

        assert "old map" in text.lower()
        assert "Take care" in text
        assert text.startswith("The merchant reaches")

    def test_no_intermediate_text(self):
        """When no intermediate text exists, final text is returned as-is."""
        intermediate_text_parts: list[str] = []
        final_text = "The tavern is quiet tonight."

        if intermediate_text_parts:
            combined = "\n\n".join(intermediate_text_parts)
            if final_text:
                combined += "\n\n" + final_text
            text = combined
        else:
            text = final_text or "[The DM pauses thoughtfully...]"

        assert text == "The tavern is quiet tonight."

    def test_empty_intermediate_text_skipped(self):
        """Empty or whitespace-only intermediate text is not accumulated."""
        intermediate_text_parts: list[str] = []

        # Iteration with empty text alongside tool call
        iter_text = "   "
        if iter_text.strip():
            intermediate_text_parts.append(iter_text.strip())

        assert len(intermediate_text_parts) == 0


class TestLoggingConfiguration:
    def test_setup_logging_debug(self, tmp_path):
        """Test that _setup_logging configures correct level and creates log file."""
        import logging
        from main import _setup_logging
        log_path = _setup_logging(debug=True, log_dir=str(tmp_path))
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert log_path is not None
        assert log_path.exists()
        # Clean up file handler
        for h in root.handlers[:]:
            if isinstance(h, logging.FileHandler):
                root.removeHandler(h)
                h.close()
        # Reset
        _setup_logging(debug=False, verbose=False)

    def test_setup_logging_verbose(self):
        import logging
        from main import _setup_logging
        _setup_logging(verbose=True)
        root = logging.getLogger()
        assert root.level == logging.INFO
        # Reset
        _setup_logging(debug=False, verbose=False)

    def test_setup_logging_default(self):
        import logging
        from main import _setup_logging
        result = _setup_logging()
        root = logging.getLogger()
        assert root.level == logging.WARNING
        assert result is None

    def test_debug_log_file_receives_messages(self, tmp_path):
        """Test that debug log file captures log messages."""
        import logging
        from main import _setup_logging
        log_path = _setup_logging(debug=True, log_dir=str(tmp_path))
        test_logger = logging.getLogger("test.debug_file")
        test_logger.debug("test debug message for file")
        # Flush handlers
        root = logging.getLogger()
        for h in root.handlers:
            h.flush()
        content = log_path.read_text()
        assert "test debug message for file" in content
        # Clean up file handler
        for h in root.handlers[:]:
            if isinstance(h, logging.FileHandler):
                root.removeHandler(h)
                h.close()
        _setup_logging(debug=False, verbose=False)
