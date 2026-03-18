"""LLM-powered adversarial player that generates game inputs."""
from __future__ import annotations

from src.dm.backends import create_backend
from scripts.debug_agent.scenarios import Scenario


_SYSTEM_TEMPLATE = """\
You are a D&D 5e player in a text adventure. You control two characters: a Fighter (Aldric) and a Wizard (Zara).

Personality: {personality}

Your goal: {goal}

Rules:
- Output ONLY your next action as a player. One or two sentences max.
- Stay in character. Do not explain your reasoning.
- Be creative and try unexpected things.
- You can address actions for either character (e.g. "Aldric attacks..." or "Zara casts...").
"""


class PlayerAI:
    """Cheap LLM that generates adversarial player inputs."""

    def __init__(
        self,
        scenario: Scenario,
        provider: str = "deepseek",
        model: str | None = None,
    ) -> None:
        self.backend = create_backend(provider, model)
        self.scenario = scenario
        self.system_prompt = _SYSTEM_TEMPLATE.format(
            personality=scenario.player_personality,
            goal=scenario.description,
        )

    def next_action(self, turn_num: int, narrative: str, state_summary: str) -> str:
        """Generate next player input. Stateless — no history accumulation."""
        user_content = (
            f"Turn {turn_num + 1}/{self.scenario.max_turns}.\n\n"
            f"Current state:\n{state_summary}\n\n"
            f"DM's last narration:\n{narrative[:1000]}\n\n"  # truncate long narrations
            f"What do you do?"
        )
        messages = [{"role": "user", "content": user_content}]

        result = self.backend.complete(
            system=self.system_prompt,
            messages=messages,
            tools=[],
            max_tokens=150,
        )
        return (result.text or "I look around.").strip()
