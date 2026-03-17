"""Tests for the world journal system — models, manager, and save/load."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.engine.game_state import GameState
from src.engine.journal_manager import JournalManager
from src.models.character import AbilityScores, Character
from src.models.combat import CombatState
from src.models.journal import JournalEntry, NpcAttitude, WorldJournal
from src.models.world import Location, WorldState


# ---------------------------------------------------------------------------
# WorldJournal model tests
# ---------------------------------------------------------------------------

class TestWorldJournal:

    def test_record_minor_event(self):
        journal = WorldJournal()
        entry = journal.record_event("Found a rusty key", location_id="dungeon_1")
        assert entry.event == "Found a rusty key"
        assert entry.importance == "minor"
        assert entry.turn == 1
        # Minor events go to location only, not global
        assert len(journal.global_entries) == 0
        assert len(journal.location_entries["dungeon_1"]) == 1

    def test_record_major_event(self):
        journal = WorldJournal()
        entry = journal.record_event(
            "Dragon defeated", location_id="lair", importance="major"
        )
        assert len(journal.global_entries) == 1
        assert len(journal.location_entries["lair"]) == 1
        assert journal.global_entries[0].event == "Dragon defeated"

    def test_turn_counter_increments(self):
        journal = WorldJournal()
        journal.record_event("A")
        journal.record_event("B")
        journal.record_event("C")
        assert journal.turn_counter == 3

    def test_update_npc_attitude_new(self):
        journal = WorldJournal()
        att = journal.update_npc_attitude("elder_mora", "friendly", "Helped her")
        assert att.disposition == "friendly"
        assert att.notes == "Helped her"

    def test_update_npc_attitude_appends_notes(self):
        journal = WorldJournal()
        journal.update_npc_attitude("elder_mora", "friendly", "Helped her")
        att = journal.update_npc_attitude("elder_mora", "hostile", "Betrayed her trust")
        assert att.disposition == "hostile"
        assert "Helped her" in att.notes
        assert "Betrayed her trust" in att.notes

    def test_world_flags(self):
        journal = WorldJournal()
        journal.set_flag("bridge_destroyed")
        journal.set_flag("secret_found", "partial")
        assert journal.get_flag("bridge_destroyed") == "true"
        assert journal.get_flag("secret_found") == "partial"
        assert journal.get_flag("nonexistent") is None

    def test_get_location_entries(self):
        journal = WorldJournal()
        for i in range(25):
            journal.record_event(f"Event {i}", location_id="tavern")
        entries = journal.get_location_entries("tavern", limit=10)
        assert len(entries) == 10
        assert entries[0].event == "Event 15"  # last 10

    def test_get_npc_entries(self):
        journal = WorldJournal()
        journal.record_event("Talked to Bram", location_id="tavern", involved_npcs=["bram"])
        journal.record_event("Fought goblins", location_id="forest")
        journal.record_event("Bram gave info", location_id="tavern", involved_npcs=["bram"])
        entries = journal.get_npc_entries("bram")
        assert len(entries) == 2

    def test_get_recent_entries(self):
        journal = WorldJournal()
        journal.record_event("A", location_id="loc1")
        journal.record_event("B", location_id="loc2")
        journal.record_event("C", location_id="loc1", importance="major")
        recent = journal.get_recent_entries(limit=5)
        assert len(recent) == 3

    def test_needs_summary_refresh(self):
        journal = WorldJournal()
        assert not journal.needs_summary_refresh(threshold=3)
        for i in range(3):
            journal.record_event(f"E{i}", location_id="loc")
        assert journal.needs_summary_refresh(threshold=3)
        journal.mark_summary_refreshed()
        assert not journal.needs_summary_refresh(threshold=3)

    def test_serialization_roundtrip(self):
        journal = WorldJournal()
        journal.record_event("Big fight", location_id="arena", importance="major", involved_npcs=["boss"])
        journal.update_npc_attitude("boss", "hostile", "Attacked party")
        journal.set_flag("arena_cleared")
        journal.global_summary = "The party cleared the arena."

        data = journal.model_dump()
        restored = WorldJournal.model_validate(data)
        assert restored.global_summary == "The party cleared the arena."
        assert len(restored.global_entries) == 1
        assert restored.npc_attitudes["boss"].disposition == "hostile"
        assert restored.world_flags["arena_cleared"] == "true"


# ---------------------------------------------------------------------------
# JournalManager tests
# ---------------------------------------------------------------------------

class TestJournalManager:

    @pytest.fixture()
    def manager(self) -> JournalManager:
        journal = WorldJournal()
        backend = MagicMock()
        backend.compress.return_value = "The party explored the tavern."
        return JournalManager(journal, backend)

    def test_record_event(self, manager: JournalManager):
        result = manager.record_event("Found a clue", location_id="tavern")
        assert result["success"] is True
        assert result["importance"] == "minor"

    def test_update_npc_attitude(self, manager: JournalManager):
        result = manager.update_npc_attitude("bram", "friendly", "Bought him ale")
        assert result["success"] is True
        assert result["disposition"] == "friendly"

    def test_set_world_flag(self, manager: JournalManager):
        result = manager.set_world_flag("door_unlocked")
        assert result["success"] is True

    def test_recall_recent(self, manager: JournalManager):
        manager.record_event("A", location_id="loc")
        manager.record_event("B", location_id="loc")
        result = manager.recall_events("recent")
        assert result["success"] is True
        assert result["count"] == 2

    def test_recall_by_location(self, manager: JournalManager):
        manager.record_event("X", location_id="dungeon")
        manager.record_event("Y", location_id="tavern")
        result = manager.recall_events("location", "dungeon")
        assert result["count"] == 1

    def test_recall_by_npc(self, manager: JournalManager):
        manager.record_event("Chat", location_id="tavern", involved_npcs=["bram"])
        result = manager.recall_events("npc", "bram")
        assert result["count"] == 1

    def test_summary_triggered_after_threshold(self, manager: JournalManager):
        manager.SUMMARY_THRESHOLD = 3
        for i in range(3):
            manager.record_event(f"Event {i}", location_id="loc")
        # Wait for background thread
        if manager._pending_summary:
            manager._pending_summary.join(timeout=5)
        assert manager.journal.global_summary == "The party explored the tavern."
        manager.backend.compress.assert_called_once()

    def test_context_block_empty(self, manager: JournalManager):
        block = manager.get_context_block("tavern")
        assert block == ""

    def test_context_block_with_data(self, manager: JournalManager):
        manager.journal.global_summary = "Party arrived in town."
        manager.journal.update_npc_attitude("bram", "friendly", "Bought ale")
        manager.record_event("Met Bram", location_id="tavern", involved_npcs=["bram"])
        block = manager.get_context_block("tavern")
        assert "Story So Far" in block
        assert "NPC Knowledge" in block
        assert "Current Location History" in block
        assert "Met Bram" in block


# ---------------------------------------------------------------------------
# GameState save/load with journal
# ---------------------------------------------------------------------------

class TestGameStateSaveLoadJournal:

    @pytest.fixture()
    def game_state(self) -> GameState:
        char = Character(
            id="test", name="Test", race="Human", class_name="Fighter",
            level=1, ability_scores=AbilityScores(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            hp=10, max_hp=10, ac=10, proficiency_bonus=2,
        )
        world = WorldState(
            current_location_id="tavern",
            locations={"tavern": Location(id="tavern", name="Tavern", description="A tavern.")},
        )
        gs = GameState(
            player_character_ids=["test"],
            characters={"test": char},
            world=world,
        )
        # Add journal data
        gs.journal.record_event("Met the innkeeper", location_id="tavern", involved_npcs=["bram"])
        gs.journal.record_event("Dragon sighted", location_id="tavern", importance="major")
        gs.journal.update_npc_attitude("bram", "friendly", "Good tipper")
        gs.journal.set_flag("tavern_visited")
        gs.journal.global_summary = "The adventurer arrived at the tavern."
        return gs

    def test_save_and_load_preserves_journal(self, game_state: GameState, tmp_path: Path):
        save_path = tmp_path / "test_save.json"
        game_state.save(save_path)

        loaded = GameState.load(save_path)
        j = loaded.journal
        assert j.global_summary == "The adventurer arrived at the tavern."
        assert j.turn_counter == 2
        assert len(j.global_entries) == 1
        assert j.global_entries[0].event == "Dragon sighted"
        assert len(j.location_entries["tavern"]) == 2
        assert j.npc_attitudes["bram"].disposition == "friendly"
        assert j.world_flags["tavern_visited"] == "true"

    def test_load_without_journal_field(self, tmp_path: Path):
        """Old save files without a journal field should load fine."""
        char = Character(
            id="test", name="Test", race="Human", class_name="Fighter",
            level=1, ability_scores=AbilityScores(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            hp=10, max_hp=10, ac=10, proficiency_bonus=2,
        )
        world = WorldState(
            current_location_id="loc",
            locations={"loc": Location(id="loc", name="Loc", description="A place.")},
        )
        # Manually create a save without journal field (old format)
        data = {
            "player_character_ids": ["test"],
            "characters": {"test": char.model_dump()},
            "world": world.model_dump(),
            "combat": {},
        }
        save_path = tmp_path / "old_save.json"
        save_path.write_text(json.dumps(data))

        loaded = GameState.load(save_path)
        assert loaded.journal.turn_counter == 0
        assert loaded.journal.global_entries == []
