"""Wire-format contracts for the OpenAI-compatible backends.

Both DeepSeek and Ollama dropped `content` from an assistant message that
carried only tool calls. The APIs reject that message, so any turn where the
DM called a tool without narrating first died mid-loop.
"""
from __future__ import annotations

import pytest

from src.dm.backends.deepseek import DeepSeekBackend
from src.dm.backends.ollama import OllamaBackend

BACKENDS = [DeepSeekBackend, OllamaBackend]

TOOL_ONLY_TURN = [
    {"role": "user", "content": "I attack."},
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t1", "name": "attack",
         "input": {"attacker_id": "aldric"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "name": "attack", "content": "{}"},
    ]},
]


def _wire(cls, messages):
    backend = cls.__new__(cls)  # skip client construction
    return cls._to_wire(backend, "system prompt", messages)


@pytest.mark.parametrize("cls", BACKENDS, ids=[c.__name__ for c in BACKENDS])
class TestAssistantContentKey:
    def test_tool_only_turn_still_has_content(self, cls):
        wire = _wire(cls, TOOL_ONLY_TURN)
        assistant = [m for m in wire if m["role"] == "assistant"]
        assert len(assistant) == 1
        assert "content" in assistant[0], "tool-only assistant message lost `content`"
        assert assistant[0]["content"] == ""
        assert assistant[0]["tool_calls"]

    def test_text_and_tools_keeps_the_text(self, cls):
        messages = [
            {"role": "user", "content": "I attack."},
            {"role": "assistant", "content": [
                {"type": "text", "text": "You lunge forward."},
                {"type": "tool_use", "id": "t1", "name": "attack", "input": {}},
            ]},
        ]
        assistant = [m for m in _wire(cls, messages) if m["role"] == "assistant"]
        assert assistant[0]["content"] == "You lunge forward."
        assert assistant[0]["tool_calls"]

    def test_every_assistant_message_has_content(self, cls):
        wire = _wire(cls, TOOL_ONLY_TURN)
        assert all("content" in m for m in wire if m["role"] == "assistant")


class TestDeepSeekStreamUsage:
    """D5: streamed responses reported zero tokens, so the context manager
    silently fell back to its character-count estimate."""

    def test_stream_requests_usage_and_reports_it(self, monkeypatch):
        captured: dict = {}

        class Delta:
            content = "Hello"
            tool_calls = None

        class Choice:
            delta = Delta()

        class ContentChunk:
            choices = [Choice()]
            usage = None

        class UsageChunk:
            choices = []

            class usage:  # noqa: N801
                prompt_tokens = 1234
                completion_tokens = 56

        class Completions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return [ContentChunk(), UsageChunk()]

        backend = DeepSeekBackend.__new__(DeepSeekBackend)
        backend.model = "deepseek-chat"
        backend._client = type("C", (), {
            "chat": type("Chat", (), {"completions": Completions()})(),
        })()

        result = backend.stream_complete("sys", [{"role": "user", "content": "hi"}], [])

        assert captured["stream_options"] == {"include_usage": True}
        assert result.usage.input_tokens == 1234
        assert result.usage.output_tokens == 56
        assert result.text == "Hello"

    def test_missing_usage_chunk_does_not_crash(self):
        class Delta:
            content = "Hi"
            tool_calls = None

        class Choice:
            delta = Delta()

        class ContentChunk:
            choices = [Choice()]
            usage = None

        class Completions:
            def create(self, **kwargs):
                return [ContentChunk()]

        backend = DeepSeekBackend.__new__(DeepSeekBackend)
        backend.model = "deepseek-chat"
        backend._client = type("C", (), {
            "chat": type("Chat", (), {"completions": Completions()})(),
        })()

        result = backend.stream_complete("sys", [{"role": "user", "content": "hi"}], [])
        assert result.usage.input_tokens == 0
