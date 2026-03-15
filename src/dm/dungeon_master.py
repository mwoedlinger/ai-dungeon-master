"""DungeonMaster — the LLM conversation loop."""
from __future__ import annotations

import json

from src.campaign.campaign_db import CampaignData
from src.dm.backends import create_backend
from src.dm.context import ContextManager
from src.dm.tools import ALL_TOOL_SCHEMAS, ToolDispatcher
from src.engine.game_state import GameState
from src.log.event_log import EventLog


class DungeonMaster:
    def __init__(
        self,
        game_state: GameState,
        campaign: CampaignData,
        event_log: EventLog,
        provider: str = "anthropic",
        model: str | None = None,
        save_path: str = "saves/autosave.json",
    ):
        self.backend = create_backend(provider, model)
        self.game_state = game_state
        self.event_log = event_log
        self.context_manager = ContextManager(campaign, game_state)
        self.tool_dispatcher = ToolDispatcher(
            game_state, event_log, save_path=save_path,
            backend=self.backend, campaign=campaign,
        )

    def process_player_input(self, player_input: str) -> str:
        """Process player input through the LLM loop, return narrative response."""
        self.context_manager.add_message({"role": "user", "content": player_input})

        while True:
            result = self.backend.complete(
                system=self.context_manager.build_system_prompt_blocks(),
                messages=self.context_manager.get_messages_for_api(),
                tools=ALL_TOOL_SCHEMAS,
                max_tokens=2048,
            )

            if not result.tool_calls:
                self.context_manager.add_message(result.raw_assistant_message)
                self.context_manager.compress_if_needed(self.backend)
                return result.text or "[The DM pauses thoughtfully...]"

            # Tool-call turn — dispatch all calls, loop back for narration
            self.context_manager.add_message(result.raw_assistant_message)

            tool_results = []
            for tc in result.tool_calls:
                outcome = self.tool_dispatcher.dispatch(tc.name, tc.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "name": tc.name,       # kept for Gemini; stripped by Anthropic backend
                    "content": json.dumps(outcome),
                })

            self.context_manager.add_message({"role": "user", "content": tool_results})
            # Loop: LLM processes results and either narrates or calls more tools

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
