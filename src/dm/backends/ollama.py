"""Ollama backend using the OpenAI-compatible HTTP API at localhost:11434."""
from __future__ import annotations

import json

from src.dm.backends.base import LLMBackend, LLMResponse, ToolCall, TokenUsage

_OLLAMA_BASE_URL = "http://localhost:11434/v1"


class OllamaBackend(LLMBackend):
    def __init__(self, model: str) -> None:
        self.model = model
        try:
            import openai
            self._client = openai.OpenAI(
                base_url=_OLLAMA_BASE_URL,
                api_key="ollama",
                timeout=120.0,
            )
        except ImportError as e:
            raise ImportError(
                "openai is required for the Ollama backend. "
                "Install it with: pip install openai>=1.0"
            ) from e

    @property
    def context_window(self) -> int:
        return 8_000

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
        """Convert normalized messages to OpenAI wire format.

        Tool results are flattened into individual role='tool' messages because
        the OpenAI API requires one message per tool result (unlike our batched
        internal format).
        """
        wire: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg["role"]
            content = msg.get("content")

            if isinstance(content, str):
                wire.append({"role": role, "content": content})
            elif isinstance(content, list) and content:
                first_type = content[0].get("type") if isinstance(content[0], dict) else None
                if first_type == "tool_result":
                    # Flatten: one message per tool result
                    for block in content:
                        wire.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block.get("content", ""),
                        })
                else:
                    # Assistant message with optional text + tool_use blocks
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

        # Extract token usage
        usage = TokenUsage()
        if hasattr(response, "usage") and response.usage:
            usage.input_tokens = getattr(response.usage, "prompt_tokens", 0)
            usage.output_tokens = getattr(response.usage, "completion_tokens", 0)

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            raw_assistant_message=raw_assistant_message,
            usage=usage,
        )
