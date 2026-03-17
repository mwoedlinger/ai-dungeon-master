"""Tests for slash command handling."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.engine.game_state import GameState
from src.interface.commands import (
    CommandContext,
    try_handle_command,
)
from src.models.character import AbilityScores, Armor, Character, Item, Weapon
from src.models.combat import CombatState
from src.models.world import Location, Quest, WorldState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_characters() -> dict[str, Character]:
    fighter = Character(
        id="aldric",
        name="Aldric Stonemantle",
        race="Human",
        class_name="Fighter",
        level=3,
        xp=900,
        ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
        hp=28,
        max_hp=28,
        ac=16,
        proficiency_bonus=2,
        skill_proficiencies=["Athletics", "Perception"],
        saving_throw_proficiencies=["STR", "CON"],
        hit_dice_remaining=3,
        hit_die_type="d10",
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
        inventory=[Item(name="Rope", quantity=1), Item(name="Torch", quantity=5)],
    )
    wizard = Character(
        id="zara",
        name="Zara Moonwhisper",
        race="Half-Elf",
        class_name="Wizard",
        level=3,
        xp=900,
        ability_scores=AbilityScores(STR=8, DEX=14, CON=12, INT=16, WIS=12, CHA=14),
        hp=19,
        max_hp=19,
        ac=13,
        proficiency_bonus=2,
        spellcasting_ability="INT",
        spell_slots={1: 4, 2: 2},
        max_spell_slots={1: 4, 2: 2},
        known_spells=["Fire Bolt", "Magic Missile", "Fireball"],
        saving_throw_proficiencies=["INT", "WIS"],
        hit_dice_remaining=3,
        hit_die_type="d6",
    )
    return {"aldric": fighter, "zara": wizard}


@pytest.fixture()
def game_state(sample_characters) -> GameState:
    world = WorldState(
        current_location_id="thornfield",
        locations={
            "thornfield": Location(id="thornfield", name="Thornfield Village", description="A muddy crossroads village.", connected_to=["bleakwood_edge"]),
            "bleakwood_edge": Location(id="bleakwood_edge", name="Edge of the Bleakwood", description="Dark forest edge.", connected_to=["thornfield"]),
        },
        quests=[
            Quest(id="q1", title="The Missing Woodcutters", description="Find the missing woodcutters.", status="active", objectives=["Search the Bleakwood"]),
        ],
    )
    return GameState(
        player_character_ids=["aldric", "zara"],
        characters=sample_characters,
        world=world,
    )


@pytest.fixture()
def ctx(game_state) -> CommandContext:
    dm = MagicMock()
    return CommandContext(game_state=game_state, dm=dm, save_path="/tmp/test_save.json")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_non_command_not_handled(ctx):
    assert try_handle_command("hello", ctx) is False


def test_slash_help(ctx, capsys):
    assert try_handle_command("/help", ctx) is True
    # Should not crash — output goes to rich console


def test_slash_save(ctx):
    with patch.object(ctx.game_state, "save") as mock_save:
        try_handle_command("/save", ctx)
        mock_save.assert_called_once_with("/tmp/test_save.json")
    assert not ctx.should_exit


def test_slash_exit(ctx):
    try_handle_command("/exit", ctx)
    assert ctx.should_exit is True
    assert ctx.should_save is False


def test_slash_quit(ctx):
    with patch.object(ctx.game_state, "save") as mock_save:
        try_handle_command("/quit", ctx)
        mock_save.assert_called_once_with("/tmp/test_save.json")
    assert ctx.should_exit is True


def test_slash_q_alias(ctx):
    with patch.object(ctx.game_state, "save"):
        try_handle_command("/q", ctx)
    assert ctx.should_exit is True


def test_slash_status(ctx):
    assert try_handle_command("/status", ctx) is True


def test_slash_map(ctx):
    assert try_handle_command("/map", ctx) is True


def test_slash_quests(ctx):
    assert try_handle_command("/quests", ctx) is True


def test_slash_inventory(ctx):
    assert try_handle_command("/inventory", ctx) is True


def test_slash_inv_alias(ctx):
    assert try_handle_command("/inv", ctx) is True


def test_character_by_name(ctx):
    """Typing /aldric should show Aldric's character sheet."""
    assert try_handle_command("/aldric", ctx) is True


def test_character_by_name_case_insensitive(ctx):
    assert try_handle_command("/Aldric", ctx) is True
    assert try_handle_command("/ZARA", ctx) is True


def test_unknown_command(ctx):
    assert try_handle_command("/foobar", ctx) is True  # handled (prints error)


def test_slash_location_shows_description(ctx):
    """/location shows the campaign description without an LLM call."""
    try_handle_command("/location", ctx)
    ctx.dm.process_player_input.assert_not_called()


def test_slash_location_with_journal_notes(ctx):
    """/location includes journal summary when available."""
    ctx.game_state.journal.location_summaries["thornfield"] = "The village is tense."
    try_handle_command("/location", ctx)
    ctx.dm.process_player_input.assert_not_called()


def test_slash_recap(ctx):
    ctx.dm.generate_session_recap.return_value = "The party rested."
    try_handle_command("/recap", ctx)
    ctx.dm.generate_session_recap.assert_called_once()
