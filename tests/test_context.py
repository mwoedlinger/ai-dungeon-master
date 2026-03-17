"""Tests for context management — compression, pruning, persistence."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.dm.context import (
    CompressResult,
    ContextManager,
    _compact_tool_exchange,
    _parse_compress_output,
)
from src.engine.game_state import GameState
from src.models.character import AbilityScores, Character
from src.models.combat import CombatState
from src.models.journal import WorldJournal
from src.models.world import Location, WorldState


def _make_game_state(journal: WorldJournal | None = None) -> GameState:
    char = Character(
        id="aldric", name="Aldric", race="Human", class_name="Fighter",
        level=3, ability_scores=AbilityScores(STR=15, DEX=12, CON=14, INT=10, WIS=10, CHA=8),
        hp=28, max_hp=28, ac=16, proficiency_bonus=2,
    )
    world = WorldState(
        current_location_id="tavern",
        locations={"tavern": Location(id="tavern", name="Tavern", description="A tavern.")},
    )
    gs = GameState(
        player_character_ids=["aldric"],
        characters={"aldric": char},
        world=world,
        journal=journal or WorldJournal(),
    )
    return gs


def _make_campaign_mock():
    campaign = MagicMock()
    campaign.get_location_context.return_value = "## Tavern\nA cozy tavern."
    return campaign


def _make_backend_mock(context_window: int = 128_000, compress_result: str = "Summary of events."):
    backend = MagicMock()
    type(backend).context_window = property(lambda self: context_window)
    backend.compress.return_value = compress_result
    return backend


# ---------------------------------------------------------------------------
# _parse_compress_output tests
# ---------------------------------------------------------------------------

class TestParseCompressOutput:

    def test_full_structured_format(self):
        text = """GLOBAL:
The party arrived at the tavern and began investigating disappearances.

LOCATIONS:
[tavern]
The party met innkeeper Bram, found a hidden passage behind the bar.
[dungeon_1]
Cleared the cellar of goblins, found a mysterious key.

NPCS:
[bram]
Friendly innkeeper. Revealed that strange noises come from the cellar at night.
[elder_mora]
Cautious elder. Offered 50gp for investigating the disappearances.

EVENTS:
- Met Bram the innkeeper
- Discovered a hidden passage behind the bar"""
        result = _parse_compress_output(text)
        assert "arrived at the tavern" in result.global_summary
        assert "tavern" in result.location_summaries
        assert "hidden passage" in result.location_summaries["tavern"]
        assert "dungeon_1" in result.location_summaries
        assert "bram" in result.npc_summaries
        assert "innkeeper" in result.npc_summaries["bram"]
        assert "elder_mora" in result.npc_summaries
        assert len(result.events) == 2

    def test_global_only(self):
        text = """GLOBAL:
The party rested at the inn. Nothing else happened.

EVENTS:
"""
        result = _parse_compress_output(text)
        assert "rested at the inn" in result.global_summary
        assert result.location_summaries == {}
        assert result.npc_summaries == {}
        assert result.events == []

    def test_malformed_no_markers(self):
        text = "Just a plain summary with no markers."
        result = _parse_compress_output(text)
        assert result.global_summary == text
        assert result.events == []

    def test_partial_sections(self):
        text = """GLOBAL:
Brief adventure summary.

LOCATIONS:
[cave]
Found treasure in the cave.

EVENTS:
- Found gold"""
        result = _parse_compress_output(text)
        assert "Brief adventure" in result.global_summary
        assert result.location_summaries == {"cave": "Found treasure in the cave."}
        assert result.npc_summaries == {}
        assert result.events == ["Found gold"]


# ---------------------------------------------------------------------------
# _compact_tool_exchange tests
# ---------------------------------------------------------------------------

class TestCompactToolExchange:

    def test_attack_roll(self):
        assistant_content = [
            {"type": "tool_use", "id": "tc1", "name": "attack",
             "input": {"attacker_id": "aldric", "target_id": "goblin_1", "weapon_name": "longsword"}},
        ]
        result_content = [
            {"type": "tool_result", "tool_use_id": "tc1",
             "content": json.dumps({"success": True, "hits": True, "damage": 8, "is_crit": False})},
        ]
        compact = _compact_tool_exchange(assistant_content, result_content)
        assert "attack" in compact
        assert "aldric" in compact
        assert "hit" in compact
        assert "8" in compact

    def test_ability_check(self):
        assistant_content = [
            {"type": "tool_use", "id": "tc2", "name": "ability_check",
             "input": {"character_id": "aldric", "ability": "STR", "skill": "Athletics", "dc": 15}},
        ]
        result_content = [
            {"type": "tool_result", "tool_use_id": "tc2",
             "content": json.dumps({"success": True, "total": 18})},
        ]
        compact = _compact_tool_exchange(assistant_content, result_content)
        assert "ability_check" in compact
        assert "Athletics" in compact
        assert "18" in compact
        assert "pass" in compact

    def test_multiple_tool_calls(self):
        assistant_content = [
            {"type": "tool_use", "id": "tc1", "name": "attack",
             "input": {"attacker_id": "a", "target_id": "b", "weapon_name": "sword"}},
            {"type": "tool_use", "id": "tc2", "name": "roll_dice",
             "input": {"dice_expr": "2d6", "reason": "damage"}},
        ]
        result_content = [
            {"type": "tool_result", "tool_use_id": "tc1",
             "content": json.dumps({"success": True, "hits": False, "is_crit": False})},
            {"type": "tool_result", "tool_use_id": "tc2",
             "content": json.dumps({"total": 7})},
        ]
        compact = _compact_tool_exchange(assistant_content, result_content)
        assert "attack" in compact
        assert "roll_dice" in compact


# ---------------------------------------------------------------------------
# ContextManager — dynamic thresholds
# ---------------------------------------------------------------------------

class TestDynamicThresholds:

    def test_small_context_window(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)
        budget, trigger = cm._thresholds(64_000)  # DeepSeek
        assert budget == 44_800  # 64k * 0.70
        assert trigger == 33_600  # 44.8k * 0.75
        assert trigger < 60_000  # must be lower than old hardcoded value

    def test_large_context_window(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)
        budget, trigger = cm._thresholds(200_000)  # Anthropic
        assert budget == 140_000
        assert trigger == 105_000


# ---------------------------------------------------------------------------
# ContextManager — compact_tool_pairs
# ---------------------------------------------------------------------------

class TestCompactToolPairs:

    def _add_tool_exchange(self, cm: ContextManager, tool_name: str = "attack"):
        """Add a tool_use → tool_result → narration exchange to history."""
        cm.add_message({
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": f"tc_{len(cm.full_history)}",
                 "name": tool_name,
                 "input": {"attacker_id": "a", "target_id": "b", "weapon_name": "sword"}},
            ],
        })
        cm.add_message({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": f"tc_{len(cm.full_history) - 1}",
                 "content": json.dumps({"success": True, "hits": True, "damage": 5})},
            ],
        })
        cm.add_message({"role": "assistant", "content": "The sword strikes true!"})

    def test_no_compaction_when_few_exchanges(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)
        self._add_tool_exchange(cm)
        self._add_tool_exchange(cm)
        original_len = len(cm.full_history)
        cm.compact_tool_pairs(keep_recent=2)
        assert len(cm.full_history) == original_len  # nothing compacted

    def test_compaction_removes_old_exchanges(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)
        # Add 4 exchanges (3 messages each = 12 messages)
        for _ in range(4):
            self._add_tool_exchange(cm)
        assert len(cm.full_history) == 12
        cm.compact_tool_pairs(keep_recent=2)
        # 2 oldest exchanges compacted: 2 * (3 msgs → 2 msgs) = save 2 messages
        assert len(cm.full_history) == 10
        # Check that compacted messages are plain strings
        assert isinstance(cm.full_history[0]["content"], str)
        assert "[Engine:" in cm.full_history[0]["content"]

    def test_keeps_recent_exchanges_intact(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)
        for _ in range(4):
            self._add_tool_exchange(cm)
        cm.compact_tool_pairs(keep_recent=2)
        # Last 6 messages (2 exchanges) should still have list content
        last_assistant = cm.full_history[-3]
        assert isinstance(last_assistant["content"], list)


# ---------------------------------------------------------------------------
# ContextManager — compress_if_needed with journal integration
# ---------------------------------------------------------------------------

class TestCompressWithJournal:

    def test_compress_stores_structured_summaries(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)

        compress_output = """GLOBAL:
The party fought goblins in the tavern cellar and won.

LOCATIONS:
[tavern]
The party cleared the cellar of goblins and found a hidden passage.

NPCS:
[bram]
Innkeeper Bram thanked the party and offered free rooms.

EVENTS:
- Defeated 3 goblins in the tavern cellar
- Found a mysterious key"""

        backend = _make_backend_mock(context_window=1000, compress_result=compress_output)

        for i in range(20):
            cm.add_message({"role": "user", "content": f"Message {i}" * 50})

        cm.compress_if_needed(backend, force=True)

        assert "fought goblins" in cm.story_summary
        assert gs.journal.conversation_summary == cm.story_summary
        # Location summary
        assert "tavern" in gs.journal.location_summaries
        assert "hidden passage" in gs.journal.location_summaries["tavern"]
        # NPC summary
        assert "bram" in gs.journal.npc_summaries
        assert "free rooms" in gs.journal.npc_summaries["bram"]
        # Events
        all_entries = gs.journal.get_recent_entries(limit=10)
        event_texts = [e.event for e in all_entries]
        assert "Defeated 3 goblins in the tavern cellar" in event_texts

    def test_compress_graceful_on_malformed_output(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)

        backend = _make_backend_mock(context_window=1000, compress_result="Just a plain summary.")

        for i in range(20):
            cm.add_message({"role": "user", "content": f"Message {i}" * 50})

        cm.compress_if_needed(backend, force=True)

        assert "plain summary" in cm.story_summary
        assert gs.journal.conversation_summary == cm.story_summary

    def test_compress_merges_with_existing_summaries(self):
        gs = _make_game_state()
        gs.journal.location_summaries["tavern"] = "Old tavern notes."
        gs.journal.npc_summaries["bram"] = "Old Bram notes."
        cm = ContextManager(_make_campaign_mock(), gs)

        compress_output = """GLOBAL:
Updated campaign summary.

LOCATIONS:
[tavern]
Updated tavern notes after the fight.

NPCS:
[bram]
Bram is now a close ally.

EVENTS:
"""
        backend = _make_backend_mock(context_window=1000, compress_result=compress_output)

        for i in range(20):
            cm.add_message({"role": "user", "content": f"Message {i}" * 50})

        cm.compress_if_needed(backend, force=True)

        # Should replace, not append (LLM already merges in the prompt)
        assert gs.journal.location_summaries["tavern"] == "Updated tavern notes after the fight."
        assert gs.journal.npc_summaries["bram"] == "Bram is now a close ally."

    def test_compress_prunes_old_entries(self):
        gs = _make_game_state()
        # Add many entries for tavern
        for i in range(20):
            gs.journal.record_event(f"Event {i}", location_id="tavern")
        gs.journal.location_summaries["tavern"] = "Summarized."
        cm = ContextManager(_make_campaign_mock(), gs)

        compress_output = """GLOBAL:
Summary.

EVENTS:
"""
        backend = _make_backend_mock(context_window=1000, compress_result=compress_output)

        for i in range(20):
            cm.add_message({"role": "user", "content": f"Message {i}" * 50})

        cm.compress_if_needed(backend, force=True)

        # Raw entries should be pruned to keep_recent=5
        assert len(gs.journal.location_entries["tavern"]) <= 5


# ---------------------------------------------------------------------------
# ContextManager — story_summary restored on init
# ---------------------------------------------------------------------------

class TestContextRestoreOnLoad:

    def test_hydrates_from_journal(self):
        journal = WorldJournal(conversation_summary="Previously on the adventure...")
        gs = _make_game_state(journal=journal)
        cm = ContextManager(_make_campaign_mock(), gs)
        assert cm.story_summary == "Previously on the adventure..."

    def test_empty_journal_gives_empty_summary(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)
        assert cm.story_summary == ""


# ---------------------------------------------------------------------------
# ContextManager — get_messages_for_api compresses before dropping
# ---------------------------------------------------------------------------

class TestGetMessagesCompressFirst:

    def test_compresses_before_trimming(self):
        gs = _make_game_state()
        cm = ContextManager(_make_campaign_mock(), gs)

        backend = _make_backend_mock(
            context_window=2000,  # very small window
            compress_result="SUMMARY:\nBrief summary.\n\nEVENTS:\n",
        )

        # Fill with messages that exceed the budget
        for i in range(30):
            cm.add_message({"role": "user", "content": f"Message {i} " * 100})

        msgs = cm.get_messages_for_api(backend)
        # Should have called compress
        backend.compress.assert_called_once()
        # Messages should be trimmed to fit
        assert len(msgs) < 30


# ---------------------------------------------------------------------------
# Save/load roundtrip for conversation_summary
# ---------------------------------------------------------------------------

class TestStructuredSummarySaveLoad:

    def test_roundtrips_through_save_load(self, tmp_path: Path):
        gs = _make_game_state()
        gs.journal.conversation_summary = "The party is resting at the inn."
        gs.journal.global_summary = "A grand adventure."
        gs.journal.location_summaries = {"tavern": "Cleared the cellar."}
        gs.journal.npc_summaries = {"bram": "Friendly innkeeper."}

        save_path = tmp_path / "test.json"
        gs.save(save_path)

        loaded = GameState.load(save_path)
        assert loaded.journal.conversation_summary == "The party is resting at the inn."
        assert loaded.journal.global_summary == "A grand adventure."
        assert loaded.journal.location_summaries["tavern"] == "Cleared the cellar."
        assert loaded.journal.npc_summaries["bram"] == "Friendly innkeeper."

    def test_backward_compat_old_saves(self, tmp_path: Path):
        """Old saves without new fields should load fine."""
        gs = _make_game_state()
        gs.journal.global_summary = "Old save."
        save_path = tmp_path / "old_save.json"
        gs.save(save_path)

        # Remove new fields from the save file
        data = json.loads(save_path.read_text())
        for field in ("conversation_summary", "location_summaries", "npc_summaries"):
            data["journal"].pop(field, None)
        save_path.write_text(json.dumps(data))

        loaded = GameState.load(save_path)
        assert loaded.journal.conversation_summary == ""
        assert loaded.journal.location_summaries == {}
        assert loaded.journal.npc_summaries == {}
        assert loaded.journal.global_summary == "Old save."


# ---------------------------------------------------------------------------
# Backend context_window property
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# WorldJournal.prune_summarized_entries
# ---------------------------------------------------------------------------

class TestPruneSummarizedEntries:

    def test_prunes_when_summary_exists(self):
        journal = WorldJournal()
        for i in range(15):
            journal.record_event(f"Event {i}", location_id="cave")
        journal.location_summaries["cave"] = "Cave was explored."
        journal.prune_summarized_entries(keep_recent=5)
        assert len(journal.location_entries["cave"]) == 5
        # Should keep the most recent 5
        assert journal.location_entries["cave"][-1].event == "Event 14"

    def test_no_prune_without_summary(self):
        journal = WorldJournal()
        for i in range(15):
            journal.record_event(f"Event {i}", location_id="cave")
        journal.prune_summarized_entries(keep_recent=5)
        # No summary for cave, so no pruning
        assert len(journal.location_entries["cave"]) == 15

    def test_prunes_global_entries(self):
        journal = WorldJournal()
        for i in range(15):
            journal.record_event(f"Major {i}", location_id="", importance="major")
        journal.global_summary = "Big picture."
        journal.prune_summarized_entries(keep_recent=5)
        assert len(journal.global_entries) == 5


# ---------------------------------------------------------------------------
# Backend context_window property
# ---------------------------------------------------------------------------

class TestBackendContextWindow:

    def test_default_backend(self):
        from src.dm.backends.base import LLMBackend
        # Create a minimal concrete subclass
        class DummyBackend(LLMBackend):
            def complete(self, system, messages, tools, max_tokens=2048):
                pass
            def compress(self, system, messages, max_tokens=1024):
                return ""
        b = DummyBackend()
        assert b.context_window == 128_000
