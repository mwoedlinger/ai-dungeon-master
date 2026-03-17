"""DeepSeek backend — OpenAI-compatible API at api.deepseek.com.

Model IDs:
  deepseek-chat      — DeepSeek-V3 (non-thinking, default)
  deepseek-reasoner  — DeepSeek-R1 (thinking; response includes reasoning_content)

Set DEEPSEEK_API_KEY in the environment.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable

from src.dm.backends.base import LLMBackend, LLMResponse, ToolCall

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekBackend(LLMBackend):
    def __init__(self, model: str) -> None:
        self.model = model

    @property
    def context_window(self) -> int:
        return 64_000
        try:
            import openai
        except ImportError as e:
            raise ImportError(
                "openai is required for the DeepSeek backend. "
                "Install it with: pip install openai>=1.0"
            ) from e
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "DEEPSEEK_API_KEY environment variable is not set."
            )
        self._client = openai.OpenAI(base_url=_DEEPSEEK_BASE_URL, api_key=api_key)

    def complete(
        self,
        system: str | list[dict],
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=self._to_wire(self._flatten_system(system), messages),
            tools=self._convert_tools(tools),  # type: ignore[arg-type]
            max_tokens=max_tokens,
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
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=self._to_wire(self._flatten_system(system), messages),
            tools=self._convert_tools(tools),  # type: ignore[arg-type]
            max_tokens=max_tokens,
            stream=True,
        )

        text_parts: list[str] = []
        # Tool call deltas arrive indexed; accumulate per-index.
        tc_accum: dict[int, dict] = {}  # idx -> {id, name, arguments}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.content:
                text_parts.append(delta.content)
                if on_text_chunk:
                    on_text_chunk(delta.content)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_accum:
                        tc_accum[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tc_accum[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc_accum[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc_accum[idx]["arguments"] += tc_delta.function.arguments

        # Build the LLMResponse from accumulated data
        text = "".join(text_parts)
        tool_calls: list[ToolCall] = []
        raw_content: list[dict] = []

        if text:
            raw_content.append({"type": "text", "text": text})

        for _idx, tc_data in sorted(tc_accum.items()):
            try:
                args = json.loads(tc_data["arguments"])
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc_data["id"], name=tc_data["name"], input=args))
            raw_content.append({
                "type": "tool_use",
                "id": tc_data["id"],
                "name": tc_data["name"],
                "input": args,
            })

        if not tool_calls:
            raw_assistant_message = {"role": "assistant", "content": text}
        else:
            raw_assistant_message = {"role": "assistant", "content": raw_content}

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            raw_assistant_message=raw_assistant_message,
        )

    def compress(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=self._to_wire(system, messages),
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]

    def _to_wire(self, system: str, messages: list[dict]) -> list[dict]:
        """Convert normalized history to OpenAI wire format."""
        wire: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg["role"]
            content = msg.get("content")

            if isinstance(content, str):
                wire.append({"role": role, "content": content})
            elif isinstance(content, list) and content:
                first_type = content[0].get("type") if isinstance(content[0], dict) else None
                if first_type == "tool_result":
                    for block in content:
                        wire.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block.get("content", ""),
                        })
                else:
                    # Assistant message with text and/or tool_use blocks
                    text = ""
                    tool_calls: list[dict] = []
                    for block in content:
                        t = block.get("type")
                        if t == "text":
                            text = block["text"]
                        elif t == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block["input"]),
                                },
                            })
                    msg_dict: dict = {"role": "assistant"}
                    if text:
                        msg_dict["content"] = text
                    if tool_calls:
                        msg_dict["tool_calls"] = tool_calls
                    wire.append(msg_dict)
            else:
                wire.append({"role": role, "content": str(content)})
        return wire

    def _from_response(self, response) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message

        # deepseek-reasoner returns reasoning_content alongside content.
        # We use only content for narration; reasoning is discarded (not replayed).
        text = message.content or ""
        tool_calls: list[ToolCall] = []
        raw_content: list[dict] = []

        if text:
            raw_content.append({"type": "text", "text": text})

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))
                raw_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": args,
                })

        if not tool_calls:
            raw_assistant_message = {"role": "assistant", "content": text}
        else:
            raw_assistant_message = {"role": "assistant", "content": raw_content}

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            raw_assistant_message=raw_assistant_message,
        )
