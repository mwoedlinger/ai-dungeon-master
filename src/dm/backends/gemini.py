"""Gemini backend using google-genai SDK (>=1.0)."""
from __future__ import annotations

import json

from src.dm.backends.base import LLMBackend, LLMResponse, ToolCall


class GeminiBackend(LLMBackend):
    def __init__(self, model: str) -> None:
        self.model = model

    @property
    def context_window(self) -> int:
        return 1_000_000  # Gemini 2.0 Flash
        try:
            from google import genai
            self._client = genai.Client()
            self._genai = genai
        except ImportError as e:
            raise ImportError(
                "google-genai is required for the Gemini backend. "
                "Install it with: pip install google-genai>=1.0"
            ) from e

    def complete(
        self,
        system: str | list[dict],
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model,
            contents=self._to_wire(messages),
            config=types.GenerateContentConfig(
                system_instruction=self._flatten_system(system),
                tools=self._convert_tools(tools),
                max_output_tokens=max_tokens,
            ),
        )
        return self._from_response(response)

    def compress(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> str:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model,
            contents=self._to_wire(messages),
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text or ""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _convert_tools(self, tools: list[dict]) -> list:
        from google.genai import types

        declarations = [
            types.FunctionDeclaration(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("input_schema"),
            )
            for t in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    def _to_wire(self, messages: list[dict]) -> list:
        from google.genai import types

        contents = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            content = msg.get("content")

            if isinstance(content, str):
                parts = [types.Part.from_text(text=content)]
            elif isinstance(content, list) and content:
                first_type = content[0].get("type") if isinstance(content[0], dict) else None
                if first_type == "tool_result":
                    # Batch all tool results into a single Content
                    parts = []
                    for block in content:
                        raw = block.get("content", "")
                        try:
                            result_obj = json.loads(raw) if isinstance(raw, str) else raw
                        except (json.JSONDecodeError, TypeError):
                            result_obj = {"result": str(raw)}
                        parts.append(types.Part.from_function_response(
                            name=block["name"],
                            response=result_obj,
                        ))
                else:
                    # Assistant content: text + tool_use blocks
                    parts = []
                    for block in content:
                        t = block.get("type")
                        if t == "text":
                            parts.append(types.Part.from_text(text=block["text"]))
                        elif t == "tool_use":
                            parts.append(types.Part(
                                function_call=types.FunctionCall(
                                    name=block["name"],
                                    args=block["input"],
                                )
                            ))
            else:
                parts = [types.Part.from_text(text=str(content))]

            contents.append(types.Content(role=role, parts=parts))
        return contents

    def _from_response(self, response) -> LLMResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        raw_content: list[dict] = []

        candidate = response.candidates[0]
        for i, part in enumerate(candidate.content.parts):
            if part.text:
                text_parts.append(part.text)
                raw_content.append({"type": "text", "text": part.text})
            elif part.function_call is not None:
                fc = part.function_call
                call_id = f"gemini_{fc.name}_{i}"
                try:
                    args = dict(fc.args)
                except Exception:
                    # Nested proto — fall back to protobuf JSON conversion
                    from google.protobuf import json_format  # type: ignore[import]
                    args = json_format.MessageToDict(fc.args)
                tool_calls.append(ToolCall(id=call_id, name=fc.name, input=args))
                raw_content.append({
                    "type": "tool_use",
                    "id": call_id,
                    "name": fc.name,
                    "input": args,
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
