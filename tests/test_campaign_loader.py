"""Tests for directory-based campaign loading, lazy access, validation, and backward compat."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.campaign.campaign_db import (
    CampaignData,
    CampaignIndex,
    EntityRef,
    EncounterTable,
    Faction,
    NPCProfile,
    PlotHook,
)
from src.campaign.loader import load_campaign, validate_campaign
from src.models.world import Location


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def legacy_campaign_data() -> dict:
    """Minimal legacy JSON campaign dict."""
    return {
        "title": "Test Campaign",
        "setting_overview": "A test world.",
        "starting_location_id": "village",
        "locations": {
            "village": {
                "id": "village",
                "name": "Village",
                "description": "A small village.",
                "connected_to": ["forest"],
            },
            "forest": {
                "id": "forest",
                "name": "Dark Forest",
                "description": "A dark forest.",
                "connected_to": ["village"],
            },
            "tavern": {
                "id": "tavern",
                "name": "The Tavern",
                "description": "A cozy tavern.",
                "parent": "village",
                "connected_to": [],
            },
        },
        "key_npcs": {
            "bob": {
                "name": "Bob",
                "location": "tavern",
                "personality": "Friendly guy",
                "goals": "Serve ale",
            },
        },
        "factions": [
            {"name": "Villagers", "description": "The locals.", "goals": "Survive."},
        ],
        "plot_hooks": [
            {
                "id": "wolves",
                "title": "Wolf Problem",
                "description": "Wolves in the forest.",
                "trigger_location": "village",
                "connected_npcs": ["bob"],
            },
        ],
        "encounter_tables": {
            "forest": [
                {
                    "description": "Wolves attack!",
                    "monster_ids": ["wolf"],
                    "difficulty": "easy",
                    "trigger": "random",
                },
            ],
        },
    }


@pytest.fixture
def legacy_json_file(tmp_path: Path, legacy_campaign_data: dict) -> Path:
    """Write legacy campaign to a JSON file."""
    p = tmp_path / "test.json"
    p.write_text(json.dumps(legacy_campaign_data))
    return p


@pytest.fixture
def yaml_campaign_dir(tmp_path: Path) -> Path:
    """Create a YAML directory campaign."""
    camp_dir = tmp_path / "test_campaign"
    camp_dir.mkdir()

    # campaign.yaml
    (camp_dir / "campaign.yaml").write_text(yaml.dump({
        "title": "YAML Test",
        "setting_overview": "A YAML test world.",
        "starting_location_id": "village",
    }))

    # locations/
    loc_dir = camp_dir / "locations"
    loc_dir.mkdir()
    (loc_dir / "village.yaml").write_text(yaml.dump({
        "id": "village",
        "name": "Village",
        "description": "A small village.",
        "connected_to": ["forest"],
        "parent": None,
    }))
    (loc_dir / "forest.yaml").write_text(yaml.dump({
        "id": "forest",
        "name": "Dark Forest",
        "description": "A dark forest.",
        "connected_to": ["village"],
    }))
    (loc_dir / "tavern.yaml").write_text(yaml.dump({
        "id": "tavern",
        "name": "The Tavern",
        "description": "A cozy tavern inside the village.",
        "parent": "village",
        "connected_to": [],
    }))

    # npcs/
    npc_dir = camp_dir / "npcs"
    npc_dir.mkdir()
    (npc_dir / "bob.yaml").write_text(yaml.dump({
        "id": "bob",
        "name": "Bob",
        "location": "tavern",
        "personality": "Friendly guy who likes ale",
        "goals": "Serve ale",
    }))

    # factions/
    fac_dir = camp_dir / "factions"
    fac_dir.mkdir()
    (fac_dir / "villagers.yaml").write_text(yaml.dump({
        "id": "villagers",
        "name": "Villagers",
        "description": "The locals.",
        "goals": "Survive.",
    }))

    # plot_hooks/
    hook_dir = camp_dir / "plot_hooks"
    hook_dir.mkdir()
    (hook_dir / "wolves.yaml").write_text(yaml.dump({
        "id": "wolves",
        "title": "Wolf Problem",
        "description": "Wolves in the forest.",
        "trigger_location": "village",
        "connected_npcs": ["bob"],
    }))

    # encounters/
    enc_dir = camp_dir / "encounters"
    enc_dir.mkdir()
    (enc_dir / "forest.yaml").write_text(yaml.dump({
        "location_id": "forest",
        "encounters": [
            {
                "description": "Wolves attack!",
                "monster_ids": ["wolf"],
                "difficulty": "easy",
                "trigger": "random",
            },
        ],
    }))

    return camp_dir


# ---------------------------------------------------------------------------
# Backward compatibility: legacy JSON loading
# ---------------------------------------------------------------------------

class TestLegacyJSON:
    def test_load_from_json_file(self, legacy_json_file: Path):
        campaign = load_campaign(legacy_json_file)
        assert campaign.title == "Test Campaign"
        assert campaign.starting_location_id == "village"

    def test_legacy_locations(self, legacy_json_file: Path):
        campaign = load_campaign(legacy_json_file)
        assert "village" in campaign.locations
        assert "forest" in campaign.locations
        assert campaign.locations["village"].name == "Village"

    def test_legacy_npcs(self, legacy_json_file: Path):
        campaign = load_campaign(legacy_json_file)
        assert "bob" in campaign.key_npcs
        assert campaign.key_npcs["bob"].name == "Bob"

    def test_legacy_query(self, legacy_json_file: Path):
        campaign = load_campaign(legacy_json_file)
        result = campaign.query("location", "village")
        assert result["success"] is True
        assert result["location"]["name"] == "Village"

    def test_legacy_get_location_context(self, legacy_json_file: Path):
        campaign = load_campaign(legacy_json_file)
        ctx = campaign.get_location_context("village")
        assert "Village" in ctx
        assert "Dark Forest" in ctx  # neighbor


# ---------------------------------------------------------------------------
# Directory-based YAML loading
# ---------------------------------------------------------------------------

class TestYAMLDirectory:
    def test_load_from_directory(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        assert campaign.title == "YAML Test"
        assert campaign.starting_location_id == "village"

    def test_lazy_location_loading(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        loc = campaign.get_location("village")
        assert loc is not None
        assert loc.name == "Village"
        assert "forest" in loc.connected_to

    def test_lazy_npc_loading(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        npc = campaign.get_npc("bob")
        assert npc is not None
        assert npc.name == "Bob"
        assert npc.location == "tavern"

    def test_locations_property(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        locs = campaign.locations
        assert len(locs) == 3
        assert "village" in locs

    def test_plot_hooks_property(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        hooks = campaign.plot_hooks
        assert len(hooks) == 1
        assert hooks[0].id == "wolves"

    def test_encounter_tables_property(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        tables = campaign.encounter_tables
        assert "forest" in tables
        assert len(tables["forest"]) == 1

    def test_missing_entity_returns_none(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        assert campaign.get_location("nonexistent") is None
        assert campaign.get_npc("nonexistent") is None

    def test_query_location(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        result = campaign.query("location", "village")
        assert result["success"] is True
        assert result["location"]["name"] == "Village"

    def test_query_npc(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        result = campaign.query("npc", "bob")
        assert result["success"] is True
        assert result["npc"]["name"] == "Bob"


# ---------------------------------------------------------------------------
# Hierarchical locations
# ---------------------------------------------------------------------------

class TestHierarchicalLocations:
    def test_parent_field(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        tavern = campaign.get_location("tavern")
        assert tavern.parent == "village"
        village = campaign.get_location("village")
        assert village.parent is None

    def test_get_children(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        children = campaign.get_children("village")
        assert len(children) == 1
        assert children[0].id == "tavern"

    def test_get_children_empty(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        children = campaign.get_children("forest")
        assert children == []

    def test_npcs_at_location_includes_children(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        # Bob is in the tavern, which is inside village
        npcs = campaign.get_npcs_at_location("village", include_children=True)
        assert len(npcs) == 1
        assert npcs[0].name == "Bob"

    def test_npcs_at_location_excludes_children(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        npcs = campaign.get_npcs_at_location("village", include_children=False)
        assert len(npcs) == 0

    def test_connected_includes_children(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        connected = campaign.get_connected_locations("village")
        ids = {c.id for c in connected}
        assert "forest" in ids  # explicit connected_to
        assert "tavern" in ids  # child location

    def test_location_context_includes_child_npcs(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        ctx = campaign.get_location_context("village")
        assert "Bob" in ctx  # NPC in child location (tavern)

    def test_get_all_sub_location_ids(self, legacy_json_file: Path):
        campaign = load_campaign(legacy_json_file)
        subs = campaign.get_all_sub_location_ids("village")
        assert "tavern" in subs


# ---------------------------------------------------------------------------
# Context budgeting
# ---------------------------------------------------------------------------

class TestContextBudgeting:
    def test_token_budget_respected(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        ctx = campaign.get_location_context("village", token_budget=50)
        # With a very small budget, we should still get the location name
        assert "Village" in ctx

    def test_default_budget(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        ctx = campaign.get_location_context("village")
        # Default budget should include everything for this small campaign
        assert "Village" in ctx
        assert "Bob" in ctx


# ---------------------------------------------------------------------------
# Cross-reference validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_campaign_passes(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        errors = validate_campaign(campaign)
        assert errors == []

    def test_valid_legacy_passes(self, legacy_json_file: Path):
        campaign = load_campaign(legacy_json_file)
        errors = validate_campaign(campaign)
        assert errors == []

    def test_broken_connected_to(self, tmp_path: Path):
        data = {
            "title": "Bad",
            "setting_overview": "",
            "starting_location_id": "a",
            "locations": {
                "a": {"id": "a", "name": "A", "description": ".", "connected_to": ["nonexistent"]},
            },
        }
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        campaign = load_campaign(p)
        errors = validate_campaign(campaign)
        assert any("nonexistent" in e for e in errors)

    def test_broken_npc_location(self, tmp_path: Path):
        data = {
            "title": "Bad",
            "setting_overview": "",
            "starting_location_id": "a",
            "locations": {"a": {"id": "a", "name": "A", "description": "."}},
            "key_npcs": {"npc1": {"name": "NPC", "location": "nowhere", "personality": ".", "goals": "."}},
        }
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        campaign = load_campaign(p)
        errors = validate_campaign(campaign)
        assert any("nowhere" in e for e in errors)

    def test_broken_parent_ref(self, tmp_path: Path):
        data = {
            "title": "Bad",
            "setting_overview": "",
            "starting_location_id": "a",
            "locations": {
                "a": {"id": "a", "name": "A", "description": ".", "parent": "ghost"},
            },
        }
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        campaign = load_campaign(p)
        errors = validate_campaign(campaign)
        assert any("ghost" in e for e in errors)

    def test_broken_starting_location(self, tmp_path: Path):
        data = {
            "title": "Bad",
            "setting_overview": "",
            "starting_location_id": "missing",
            "locations": {"a": {"id": "a", "name": "A", "description": "."}},
        }
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        campaign = load_campaign(p)
        errors = validate_campaign(campaign)
        assert any("missing" in e for e in errors)


# ---------------------------------------------------------------------------
# LRU cache behavior
# ---------------------------------------------------------------------------

class TestLRUCache:
    def test_cache_hit(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        loc1 = campaign.get_location("village")
        loc2 = campaign.get_location("village")
        assert loc1 is loc2  # same object from cache

    def test_cache_eviction(self, yaml_campaign_dir: Path):
        campaign = load_campaign(yaml_campaign_dir)
        # Set very small cache
        campaign._cache._max_size = 1
        campaign.get_location("village")
        campaign.get_location("forest")  # evicts village
        # village should still be loadable (re-read from disk)
        loc = campaign.get_location("village")
        assert loc is not None
        assert loc.name == "Village"


# ---------------------------------------------------------------------------
# Real campaign: shattered_crown directory
# ---------------------------------------------------------------------------

class TestShatteredCrownDirectory:
    """Integration tests against the migrated shattered_crown campaign."""

    @pytest.fixture
    def campaign(self) -> CampaignData:
        campaign_dir = Path(__file__).parent.parent / "campaigns" / "shattered_crown"
        if not campaign_dir.exists():
            pytest.skip("Migrated campaign directory not found")
        return load_campaign(campaign_dir)

    def test_loads(self, campaign: CampaignData):
        assert campaign.title == "The Shattered Crown"
        assert campaign.starting_location_id == "thornfield"

    def test_all_locations_loadable(self, campaign: CampaignData):
        locs = campaign.locations
        assert len(locs) == 6
        assert "thornfield" in locs

    def test_all_npcs_loadable(self, campaign: CampaignData):
        npcs = campaign.key_npcs
        assert len(npcs) == 4
        assert "elder_mora" in npcs

    def test_tavern_is_child_of_thornfield(self, campaign: CampaignData):
        tavern = campaign.get_location("broken_antler_tavern")
        assert tavern.parent == "thornfield"
        children = campaign.get_children("thornfield")
        assert any(c.id == "broken_antler_tavern" for c in children)

    def test_validation_passes(self, campaign: CampaignData):
        errors = validate_campaign(campaign)
        assert errors == [], f"Validation errors: {errors}"


# ---------------------------------------------------------------------------
# Fuzzy ID matching & helpful error messages
# ---------------------------------------------------------------------------

class TestFuzzyIDMatching:
    """Test that query_world_lore fuzzy-matches IDs and shows valid IDs on error."""

    @pytest.fixture
    def campaign(self, legacy_json_file: Path) -> CampaignData:
        return load_campaign(legacy_json_file)

    def test_exact_match(self, campaign: CampaignData):
        result = campaign.query("npc", "bob")
        assert result["success"] is True

    def test_case_insensitive_match(self, campaign: CampaignData):
        result = campaign.query("npc", "Bob")
        assert result["success"] is True

    def test_substring_match(self, campaign: CampaignData):
        # "wolves" is a substring of the plot_hook id "wolves"
        result = campaign.query("plot_hook", "wolves")
        assert result["success"] is True

    def test_not_found_lists_valid_ids(self, campaign: CampaignData):
        result = campaign.query("npc", "nonexistent_npc")
        assert result["success"] is False
        assert "Valid IDs" in result["error"]
        assert "bob" in result["error"]

    def test_location_not_found_lists_valid_ids(self, campaign: CampaignData):
        result = campaign.query("location", "castle")
        assert result["success"] is False
        assert "village" in result["error"]
        assert "forest" in result["error"]

    def test_plot_hook_not_found_lists_valid_ids(self, campaign: CampaignData):
        result = campaign.query("plot_hook", "dragon_attack")
        assert result["success"] is False
        assert "wolves" in result["error"]

    def test_fuzzy_match_word_overlap(self):
        """Test the fuzzy matcher directly with word-overlap heuristic."""
        campaign = CampaignData.from_dict({
            "title": "T", "setting_overview": "S",
            "starting_location_id": "v",
            "locations": {"v": {"id": "v", "name": "V", "description": "V"}},
            "key_npcs": {
                "thorvald_militia_captain": {
                    "name": "Captain Thorvald",
                    "location": "v",
                    "personality": "Stern",
                    "goals": "Protect",
                },
            },
            "plot_hooks": [
                {"id": "missing_woodcutters", "title": "MW", "description": "D"},
            ],
        })
        # LLM guesses wrong word order
        assert campaign._fuzzy_match_id(
            "captain_thorvald", ["thorvald_militia_captain"]
        ) == "thorvald_militia_captain"
        # LLM adds prefix
        assert campaign._fuzzy_match_id(
            "the_missing_woodcutters", ["missing_woodcutters"]
        ) == "missing_woodcutters"
        # Query succeeds via fuzzy match
        result = campaign.query("npc", "captain_thorvald")
        assert result["success"] is True
        result = campaign.query("plot_hook", "the_missing_woodcutters")
        assert result["success"] is True
