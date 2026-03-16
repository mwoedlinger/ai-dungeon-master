"""Base class and normalized types for LLM backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    raw_assistant_message: dict  # normalized, ready to append to history


class LLMBackend(ABC):
    @abstractmethod
    def complete(
        self,
        system: str | list[dict],
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse: ...

    def stream_complete(
        self,
        system: str | list[dict],
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
        on_text_chunk: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Streaming variant of complete. Default falls back to non-streaming."""
        result = self.complete(system, messages, tools, max_tokens)
        if on_text_chunk and result.text:
            on_text_chunk(result.text)
        return result

    def generate(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> str:
        """Text generation using the main model without tools.

        Used for creative tasks like campaign generation where we want the
        full model's capability but don't need tool calling.
        Default implementation delegates to complete() with empty tools.
        """
        result = self.complete(system, messages, tools=[], max_tokens=max_tokens)
        return result.text

    @abstractmethod
    def compress(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> str: ...

    @staticmethod
    def _flatten_system(system: str | list[dict]) -> str:
        """Flatten a structured system prompt (list of blocks) to a plain string."""
        if isinstance(system, str):
            return system
        return "\n\n".join(b.get("text", "") for b in system if isinstance(b, dict))
