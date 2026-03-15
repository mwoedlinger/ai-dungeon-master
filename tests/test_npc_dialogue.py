"""Tests for NPC dialogue sub-agent."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.campaign.campaign_db import CampaignData, NPCProfile
from src.dm.npc_dialogue import NPCDialogueSession


@dataclass
class _FakeResponse:
    text: str
    tool_calls: list = None
    raw_assistant_message: dict = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []
        if self.raw_assistant_message is None:
            self.raw_assistant_message = {"role": "assistant", "content": self.text}


class FakeBackend:
    """Minimal LLM backend stub for testing."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or ["Greetings, traveler."])
        self._call_count = 0
        self.last_system: str | None = None
        self.last_messages: list[dict] | None = None

    def complete(self, system, messages, tools, max_tokens=512):
        self.last_system = system if isinstance(system, str) else "\n".join(
            b.get("text", "") for b in system if isinstance(b, dict)
        )
        self.last_messages = messages
        idx = min(self._call_count, len(self.responses) - 1)
        self._call_count += 1
        return _FakeResponse(text=self.responses[idx])

    def compress(self, system, messages, max_tokens=200):
        return "Summary of conversation."


@pytest.fixture
def npc() -> NPCProfile:
    return NPCProfile(
        id="elder_mora",
        name="Elder Mora",
        location="village_square",
        personality="Wise, cautious, speaks in riddles",
        goals="Protect the village from the encroaching darkness",
        secret="She is secretly a retired adventurer who sealed the demon lord 40 years ago",
        disposition="friendly",
    )


@pytest.fixture
def campaign() -> CampaignData:
    return CampaignData(
        title="Test Campaign",
        setting_overview="A dark fantasy world where an ancient evil stirs.",
        starting_location_id="village_square",
    )


class TestNPCDialogueSession:
    def test_system_prompt_contains_personality(self, npc, campaign):
        backend = FakeBackend()
        session = NPCDialogueSession(npc=npc, backend=backend, campaign=campaign)
        session.respond("Hello")
        assert "Wise, cautious" in backend.last_system

    def test_system_prompt_hides_secret(self, npc, campaign):
        backend = FakeBackend()
        session = NPCDialogueSession(npc=npc, backend=backend, campaign=campaign)
        prompt = session._system_prompt
        # Secret should be in "hidden" section, not volunteered
        assert "do NOT reveal" in prompt.lower() or "do not reveal" in prompt.lower()
        assert npc.secret in prompt

    def test_respond_returns_text(self, npc, campaign):
        backend = FakeBackend(["Ah, welcome young one."])
        session = NPCDialogueSession(npc=npc, backend=backend, campaign=campaign)
        result = session.respond("Who are you?")
        assert result == "Ah, welcome young one."

    def test_context_injected(self, npc, campaign):
        backend = FakeBackend()
        session = NPCDialogueSession(npc=npc, backend=backend, campaign=campaign)
        session.respond("Tell me your secret", context="Insight check succeeded (DC 15, rolled 18)")
        assert "DM context" in backend.last_messages[0]["content"]
        assert "Insight check succeeded" in backend.last_messages[0]["content"]

    def test_continue_reuses_history(self, npc, campaign):
        backend = FakeBackend(["First reply", "Second reply"])
        session = NPCDialogueSession(npc=npc, backend=backend, campaign=campaign)
        session.respond("Hello")
        session.respond("Tell me more")
        assert len(session.history) == 4  # 2 user + 2 assistant
        assert session.turn_count == 2

    def test_max_turns_limit(self, npc, campaign):
        backend = FakeBackend(["reply"] * 10)
        session = NPCDialogueSession(npc=npc, backend=backend, campaign=campaign)
        for i in range(NPCDialogueSession.MAX_TURNS):
            session.respond(f"Question {i}")
        # Next response should be the wind-down message
        result = session.respond("One more question")
        assert "said all they want" in result

    def test_summarize(self, npc, campaign):
        backend = FakeBackend(["The village is in danger."])
        session = NPCDialogueSession(npc=npc, backend=backend, campaign=campaign)
        session.respond("What's going on?")
        summary = session.summarize()
        assert summary == "Summary of conversation."

    def test_no_secret_npc(self, campaign):
        npc = NPCProfile(
            id="guard",
            name="Town Guard",
            location="gate",
            personality="Dutiful, bored",
            goals="Keep watch",
            disposition="neutral",
        )
        backend = FakeBackend()
        session = NPCDialogueSession(npc=npc, backend=backend, campaign=campaign)
        prompt = session._system_prompt
        assert "Secret" not in prompt
        assert "HIDDEN" not in prompt
