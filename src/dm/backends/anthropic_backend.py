"""Anthropic backend — wraps the anthropic SDK."""
from __future__ import annotations

from collections.abc import Callable

import anthropic as _anthropic

from src.dm.backends.base import LLMBackend, LLMResponse, ToolCall

_COMPRESS_MODEL = "claude-haiku-4-5-20251001"


class AnthropicBackend(LLMBackend):
    def __init__(self, model: str) -> None:
        self.model = model
        self._client = _anthropic.Anthropic()

    def complete(
        self,
        system: str | list[dict],
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        response = self._client.messages.create(
            model=self.model,
            system=system,  # list[dict] passes cache_control blocks; str also accepted
            messages=self._to_wire(messages),
            tools=tools,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )
        return self._from_response(response)

    def stream_complete(
        self,
        system: str | list[dict],
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
        on_text_chunk: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        with self._client.messages.stream(
            model=self.model,
            system=system,
            messages=self._to_wire(messages),
            tools=tools,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        ) as stream:
            if on_text_chunk:
                for text in stream.text_stream:
                    on_text_chunk(text)
            response = stream.get_final_message()
        return self._from_response(response)

    def generate(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> str:
        response = self._client.messages.create(
            model=self.model,
            system=system,
            messages=self._to_wire(messages),
            max_tokens=max_tokens,
        )
        return response.content[0].text

    def compress(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> str:
        response = self._client.messages.create(
            model=_COMPRESS_MODEL,
            system=system,
            messages=self._to_wire(messages),
            max_tokens=max_tokens,
        )
        return response.content[0].text

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _to_wire(self, messages: list[dict]) -> list[dict]:
        """Strip fields Anthropic doesn't accept (name on tool_result blocks)."""
        result = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                new_blocks = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        block = {k: v for k, v in block.items() if k != "name"}
                    new_blocks.append(block)
                result.append({"role": msg["role"], "content": new_blocks})
            else:
                result.append(msg)
        return result

    def _from_response(self, response) -> LLMResponse:
        """Convert Anthropic SDK response to normalized LLMResponse."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        raw_content: list[dict] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
                raw_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    input=dict(block.input),
                ))
                raw_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": dict(block.input),
                })

        if not tool_calls:
            raw_assistant_message = {"role": "assistant", "content": "".join(text_parts)}
        else:
            raw_assistant_message = {"role": "assistant", "content": raw_content}

        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            raw_assistant_message=raw_assistant_message,
        )
