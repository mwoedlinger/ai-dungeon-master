"""Tests for the multi-pass campaign generator (non-LLM components)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.generate_campaign import (
    CampaignGenerator,
    NPC_ARCHETYPES,
    extract_json,
    get_srd_monsters_by_cr,
    validate_cross_references,
    validate_location_graph,
)


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------

class TestExtractJson:

    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_fenced(self):
        text = '```json\n{"a": 1}\n```'
        assert extract_json(text) == {"a": 1}

    def test_surrounded_by_text(self):
        text = 'Here is the JSON:\n{"a": 1}\nDone.'
        assert extract_json(text) == {"a": 1}

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            extract_json("no json here")


# ---------------------------------------------------------------------------
# validate_location_graph
# ---------------------------------------------------------------------------

class TestValidateLocationGraph:

    def test_connected_graph(self):
        locs = {
            "a": {"connected_to": ["b"]},
            "b": {"connected_to": ["a", "c"]},
            "c": {"connected_to": ["b"]},
        }
        assert validate_location_graph(locs) == []

    def test_disconnected_node(self):
        locs = {
            "a": {"connected_to": ["b"]},
            "b": {"connected_to": ["a"]},
            "c": {"connected_to": []},
        }
        errors = validate_location_graph(locs)
        assert any("Unreachable" in e for e in errors)

    def test_invalid_reference(self):
        locs = {
            "a": {"connected_to": ["b", "nonexistent"]},
            "b": {"connected_to": ["a"]},
        }
        errors = validate_location_graph(locs)
        assert any("nonexistent" in e for e in errors)

    def test_empty(self):
        assert len(validate_location_graph({})) > 0


# ---------------------------------------------------------------------------
# validate_cross_references
# ---------------------------------------------------------------------------

class TestValidateCrossReferences:

    def test_valid_campaign(self):
        campaign = {
            "locations": {"tavern": {}, "forest": {}},
            "key_npcs": {"bram": {"location": "tavern"}},
            "plot_hooks": [
                {"id": "h1", "trigger_location": "tavern", "connected_npcs": ["bram"],
                 "clue_locations": ["forest"]}
            ],
            "encounter_tables": {},
        }
        assert validate_cross_references(campaign) == []

    def test_npc_bad_location(self):
        campaign = {
            "locations": {"tavern": {}},
            "key_npcs": {"bram": {"location": "nonexistent"}},
            "plot_hooks": [],
            "encounter_tables": {},
        }
        errors = validate_cross_references(campaign)
        assert any("bram" in e and "nonexistent" in e for e in errors)

    def test_hook_bad_npc(self):
        campaign = {
            "locations": {"tavern": {}},
            "key_npcs": {},
            "plot_hooks": [
                {"id": "h1", "trigger_location": "tavern",
                 "connected_npcs": ["ghost"], "clue_locations": []}
            ],
            "encounter_tables": {},
        }
        errors = validate_cross_references(campaign)
        assert any("ghost" in e for e in errors)


# ---------------------------------------------------------------------------
# SRD monster query
# ---------------------------------------------------------------------------

class TestSrdMonsterQuery:

    def test_cr_range_filter(self):
        monsters = get_srd_monsters_by_cr(0, 1)
        assert len(monsters) > 0
        assert all(m["cr"] <= 1 for m in monsters)

    def test_high_cr_range(self):
        monsters = get_srd_monsters_by_cr(10, 20)
        assert len(monsters) > 0
        assert all(m["cr"] >= 10 for m in monsters)

    def test_result_format(self):
        monsters = get_srd_monsters_by_cr(0.25, 0.25)
        assert len(monsters) > 0
        m = monsters[0]
        assert "index" in m
        assert "name" in m
        assert "cr" in m
        assert "type" in m


# ---------------------------------------------------------------------------
# NPC archetypes
# ---------------------------------------------------------------------------

def test_npc_archetypes_diversity():
    """Ensure we have enough varied archetypes."""
    assert len(NPC_ARCHETYPES) >= 6
    # Each archetype should be meaningfully different (>50 chars)
    for arch in NPC_ARCHETYPES:
        assert len(arch) > 50


# ---------------------------------------------------------------------------
# CampaignGenerator assembly & validation
# ---------------------------------------------------------------------------

class TestCampaignGeneratorAssembly:

    def _make_generator(self) -> CampaignGenerator:
        backend = MagicMock()
        return CampaignGenerator(backend, verbose=False)

    def test_assemble_produces_valid_structure(self):
        gen = self._make_generator()
        concept = {
            "title": "Test Campaign",
            "setting_overview": "A dark place.",
        }
        locations_data = {
            "starting_location_id": "tavern",
            "locations": {
                "tavern": {
                    "name": "The Tavern", "description": "Cozy.",
                    "connected_to": ["forest"],
                    "narrative_role": "introduction",
                    "atmosphere": "Warm.", "hidden_detail": "Trapdoor.",
                },
                "forest": {
                    "name": "Dark Forest", "description": "Spooky.",
                    "connected_to": ["tavern"],
                    "narrative_role": "investigation",
                    "atmosphere": "Cold.", "hidden_detail": "Old shrine.",
                },
            },
        }
        people_data = {
            "key_npcs": {
                "bram": {
                    "name": "Bram", "location": "tavern",
                    "personality": "Cheerful.", "goals": "Survive.",
                    "secret": "Saw something.", "disposition": "friendly",
                    "wants_from_party": "Help", "knows_about": [],
                },
            },
            "factions": [
                {"name": "Villagers", "description": "Local folk.",
                 "goals": "Peace.", "public_face": "Friendly.",
                 "allies": [], "enemies": []},
            ],
        }
        hooks_data = {
            "plot_hooks": [
                {"id": "h1", "title": "Mystery", "description": "Something wrong.",
                 "trigger_location": "tavern", "connected_npcs": ["bram"],
                 "actual_situation": "Bad stuff.", "connects_to": [],
                 "clue_locations": ["forest"]},
            ],
        }
        encounters = {
            "forest": [
                {"description": "Wolves attack.", "monster_ids": ["wolf", "wolf"],
                 "difficulty": "easy", "trigger": "random",
                 "narrative_context": "Hungry wolves."},
            ],
        }

        campaign = gen._assemble(concept, locations_data, people_data, hooks_data, encounters)

        assert campaign["title"] == "Test Campaign"
        assert "tavern" in campaign["locations"]
        assert "bram" in campaign["key_npcs"]
        assert len(campaign["factions"]) == 1
        assert len(campaign["plot_hooks"]) == 1
        assert "forest" in campaign["encounter_tables"]

        # Extra fields should be stripped
        assert "narrative_role" not in campaign["locations"]["tavern"]
        assert "wants_from_party" not in campaign["key_npcs"]["bram"]
        assert "narrative_context" not in campaign["encounter_tables"]["forest"][0]

    def test_auto_fix_bad_npc_location(self):
        gen = self._make_generator()
        campaign = {
            "starting_location_id": "tavern",
            "locations": {"tavern": {}, "forest": {}},
            "key_npcs": {"bram": {"location": "nonexistent"}},
            "plot_hooks": [],
            "encounter_tables": {},
            "factions": [],
        }
        fixed = gen._auto_fix(campaign, ["NPC location error"])
        assert campaign["key_npcs"]["bram"]["location"] == "tavern"
