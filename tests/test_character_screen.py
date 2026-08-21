"""Interactive character screen (docs/DESIGN_INVENTORY_UI.md)."""
from __future__ import annotations

import io

import pytest
from rich.console import Console

from src.engine.game_state import GameState
from src.interface.cli import build_character_sheet
from src.interface.screens.character_screen import run_character_screen
from src.models.character import AbilityScores, Armor, Character, Weapon
from src.models.world import WorldState


def _keys(seq):
    it = iter(seq)
    return lambda: next(it, "cancel")


@pytest.fixture
def quiet_console() -> Console:
    return Console(file=io.StringIO(), width=100)


def _pc(cid, name, **over):
    base = dict(
        id=cid, name=name, race="Human", class_name="Fighter",
        ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
        hp=12, max_hp=30, ac=16, proficiency_bonus=2,
        hit_dice_remaining=3, hit_die_type="d10",
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
    )
    base.update(over)
    return Character(**base)


@pytest.fixture
def party_gs() -> GameState:
    aldric = _pc("aldric", "Aldric")
    mara = _pc("mara", "Mara", hp=30)
    world = WorldState(current_location_id="loc", locations={})
    return GameState(player_character_ids=["aldric", "mara"],
                     characters={"aldric": aldric, "mara": mara}, world=world)


def test_sheet_builder_contains_core_fields(party_gs):
    sheet = build_character_sheet(party_gs.characters["aldric"])
    assert "Aldric" in sheet and "Ability Scores" in sheet and "Longsword" in sheet


class TestCharacterScreen:
    def test_long_rest_restores_hp(self, party_gs, quiet_console):
        # Actions order: Manage inventory(0), Short rest(1), Long rest(2), Switch(3).
        keys = ["down", "down", "enter",  # choose Long rest
                "enter",                    # confirm "Yes" (first option)
                "cancel"]                   # leave screen
        run_character_screen(party_gs, console=quiet_console, read_key=_keys(keys), char_id="aldric")
        assert party_gs.characters["aldric"].hp == 30

    def test_short_rest_spends_hit_dice(self, party_gs, quiet_console):
        keys = ["down", "enter",  # Short rest
                "enter",           # spend 1 hit die (first option)
                "cancel"]
        run_character_screen(party_gs, console=quiet_console, read_key=_keys(keys), char_id="aldric")
        aldric = party_gs.characters["aldric"]
        assert aldric.hit_dice_remaining == 2 and aldric.hp > 12

    def test_rests_disabled_in_combat(self, party_gs, quiet_console):
        party_gs.combat.active = True
        # Short rest (idx 1) is disabled; Enter on it must not heal/spend dice.
        keys = ["down", "enter", "cancel"]
        run_character_screen(party_gs, console=quiet_console, read_key=_keys(keys), char_id="aldric")
        aldric = party_gs.characters["aldric"]
        assert aldric.hit_dice_remaining == 3 and aldric.hp == 12

    def test_switch_character_then_back(self, party_gs, quiet_console):
        # Switch is the 4th action (idx 3); pick Mara, then back out.
        keys = ["down", "down", "down", "enter",  # Switch character
                "enter",                            # pick Mara (only other PC)
                "cancel"]                           # leave
        run_character_screen(party_gs, console=quiet_console, read_key=_keys(keys), char_id="aldric")
        # No state change expected; just exercising navigation without error.
        assert party_gs.characters["mara"].hp == 30
