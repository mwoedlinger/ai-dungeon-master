"""Base class and normalized types for LLM backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
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
