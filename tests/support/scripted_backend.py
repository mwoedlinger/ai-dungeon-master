"""A scripted LLMBackend for driving the DM loop without an API.

The real backends are the only thing standing between a test and
`DungeonMaster.process_player_input`. This double replaces them with a fixed
list of turns, so a test can assert on what the engine did rather than on what
a model happened to say.

Three details are load-bearing and easy to get wrong (see
`anthropic_backend._from_response` for the shapes being mirrored):

1. ``usage`` must be a real :class:`TokenUsage` — the DM reads four attributes
   off it on every call.
2. ``raw_assistant_message`` carries plain string content when there are no
   tool calls and a list of blocks when there are. `compact_tool_pairs` keys on
   ``content`` being a list.
3. ``tool_use`` ids must be unique and stable — `_compact_tool_exchange`
   matches results back to calls by id.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.dm.backends.base import LLMBackend, LLMResponse, TokenUsage


@dataclass
class ScriptedTurn:
    """One scripted model response."""
    text: str = ""
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    usage: TokenUsage = field(
        default_factory=lambda: TokenUsage(input_tokens=100, output_tokens=50),
    )


class ScriptedBackend(LLMBackend):
    """Replays `turns` in order, recording every request it was given."""

    def __init__(
        self,
        turns: list[ScriptedTurn],
        context_window: int = 128_000,
        compress_output: str = "GLOBAL: Summary of the session so far.",
        on_call: Callable[[int], None] | None = None,
    ):
        self.turns = list(turns)
        self._context_window = context_window
        self.compress_output = compress_output
        self.compress_calls: list[dict] = []
        self._on_call = on_call
        # Every api_kwargs this backend was handed, for assertions.
        self.calls: list[dict] = []
        self.model = "scripted-1"

    # -- constructors ---------------------------------------------------------

    @classmethod
    def narration(cls, *texts: str, **kwargs) -> "ScriptedBackend":
        """Pure narration, no tool calls."""
        return cls([ScriptedTurn(text=t) for t in texts], **kwargs)

    @classmethod
    def tools_then_narration(
        cls,
        tool_calls: list[tuple[str, dict]],
        text: str,
        first_text: str = "",
        **kwargs,
    ) -> "ScriptedBackend":
        """The canonical two-call shape: resolve tools, then narrate."""
        return cls(
            [
                ScriptedTurn(text=first_text, tool_calls=tool_calls),
                ScriptedTurn(text=text),
            ],
            **kwargs,
        )

    # -- LLMBackend -----------------------------------------------------------

    @property
    def context_window(self) -> int:
        return self._context_window

    def complete(self, system, messages, tools, max_tokens: int = 2048) -> LLMResponse:
        idx = len(self.calls)
        self.calls.append({
            "system": system,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
        })
        if self._on_call is not None:
            self._on_call(idx)
        if idx >= len(self.turns):
            raise AssertionError(
                f"ScriptedBackend exhausted: the DM made {idx + 1} calls but only "
                f"{len(self.turns)} turn(s) were scripted. Add another ScriptedTurn."
            )
        return self._to_response(self.turns[idx], idx)

    def compress(self, system, messages, max_tokens: int = 1024) -> str:
        self.compress_calls.append({"system": system, "messages": messages})
        return self.compress_output

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _to_response(turn: ScriptedTurn, call_idx: int) -> LLMResponse:
        from src.dm.backends.base import ToolCall

        if not turn.tool_calls:
            return LLMResponse(
                text=turn.text,
                tool_calls=[],
                # No tools -> plain string content, as the real backends emit.
                raw_assistant_message={"role": "assistant", "content": turn.text},
                usage=turn.usage,
            )

        calls, blocks = [], []
        if turn.text:
            blocks.append({"type": "text", "text": turn.text})
        for i, (name, inputs) in enumerate(turn.tool_calls):
            tool_id = f"toolu_{call_idx:04d}_{i}"
            calls.append(ToolCall(id=tool_id, name=name, input=inputs))
            blocks.append({
                "type": "tool_use", "id": tool_id, "name": name, "input": inputs,
            })
        return LLMResponse(
            text=turn.text,
            tool_calls=calls,
            raw_assistant_message={"role": "assistant", "content": blocks},
            usage=turn.usage,
        )
