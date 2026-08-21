"""Menu primitive + interactive-inventory screen (docs/DESIGN_INVENTORY_UI.md)."""
from __future__ import annotations

import io

import pytest
from rich.console import Console

from src.engine.game_state import GameState
from src.interface.screens.inventory_screen import run_inventory_screen
from src.interface.screens.menu import (
    MenuOption,
    _assemble_key,
    _semantic,
    interactive_enabled,
    interactive_status,
    select,
)
from src.models.character import AbilityScores, Armor, Character, Item, Weapon
from src.models.world import WorldState


def _keys(seq):
    """A read_key callable that yields *seq* then 'cancel' forever (safety net)."""
    it = iter(seq)

    def read_key() -> str:
        return next(it, "cancel")

    return read_key


@pytest.fixture
def quiet_console() -> Console:
    return Console(file=io.StringIO(), width=80)


class TestSelect:
    def test_navigate_down_and_select(self, quiet_console):
        opts = [MenuOption(label=str(i), value=i) for i in range(3)]
        chosen = select("t", opts, console=quiet_console, read_key=_keys(["down", "down", "enter"]))
        assert chosen == 2

    def test_up_wraps_to_last(self, quiet_console):
        opts = [MenuOption(label=str(i), value=i) for i in range(3)]
        chosen = select("t", opts, console=quiet_console, read_key=_keys(["up", "enter"]))
        assert chosen == 2

    def test_cancel_returns_none(self, quiet_console):
        opts = [MenuOption(label="a", value="a")]
        assert select("t", opts, console=quiet_console, read_key=_keys(["cancel"])) is None

    def test_empty_options_returns_none(self, quiet_console):
        assert select("t", [], console=quiet_console, read_key=_keys([])) is None

    def test_skips_disabled_rows(self, quiet_console):
        opts = [
            MenuOption(label="a", value="a"),
            MenuOption(label="b", value="b", enabled=False),
            MenuOption(label="c", value="c"),
        ]
        chosen = select("t", opts, console=quiet_console, read_key=_keys(["down", "enter"]))
        assert chosen == "c"  # the disabled row is hopped over


class TestKeyAssembly:
    """The lone-Esc fix: Esc must resolve to cancel without waiting for more bytes."""

    def _reader(self, chars):
        it = iter(chars)
        return lambda: next(it)

    def test_lone_esc_returns_immediately(self):
        # Esc pressed, nothing else waiting -> bare Esc (not a blocked read).
        key = _assemble_key(self._reader(["\x1b"]), lambda: False)
        assert key == "\x1b"
        assert _semantic(key) == "cancel"

    def test_arrow_sequence_assembled(self):
        key = _assemble_key(self._reader(["\x1b", "[", "A"]), lambda: True)
        assert key == "\x1b[A"
        assert _semantic(key) == "up"

    def test_plain_char_passthrough(self):
        key = _assemble_key(self._reader(["j"]), lambda: False)
        assert key == "j" and _semantic(key) == "down"


def test_interactive_disabled_under_piped_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert interactive_enabled() is False


def test_status_reports_reason_for_non_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    ok, reason = interactive_status()
    assert ok is False and "terminal" in reason


def test_status_ok_when_tty_and_readchar(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    ok, reason = interactive_status()
    assert ok is True and reason == ""


def _pc(cid, name, **over):
    base = dict(
        id=cid, name=name, race="Human", class_name="Fighter",
        ability_scores=AbilityScores(STR=14, DEX=12, CON=12, INT=10, WIS=10, CHA=10),
        hp=20, max_hp=30, ac=16, proficiency_bonus=2,
    )
    base.update(over)
    return Character(**base)


@pytest.fixture
def solo_gs() -> GameState:
    aldric = _pc(
        "aldric", "Aldric", gold=10,
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
        inventory=[Item(name="Healing Potion", quantity=2, weight=0.5, properties={"heal": "2d4+2"})],
    )
    world = WorldState(current_location_id="loc", locations={})
    return GameState(player_character_ids=["aldric"],
                     characters={"aldric": aldric}, world=world)


class TestInventoryScreen:
    def test_use_potion_through_screen(self, solo_gs, quiet_console):
        # Items order: Longsword (0), Chain Mail (1), Healing Potion (2).
        # Navigate to the potion, open its action menu, choose Use (EXAMINE=0, USE=1),
        # then Esc out of the item list.
        keys = ["down", "down", "enter",   # select Healing Potion
                "down", "enter",            # action menu: EXAMINE -> USE
                "cancel"]                   # leave item list
        run_inventory_screen(solo_gs, console=quiet_console, read_key=_keys(keys))
        aldric = solo_gs.characters["aldric"]
        assert aldric.hp > 20
        potion = next(it for it in aldric.inventory if it.name == "Healing Potion")
        assert potion.quantity == 1

    def test_back_out_immediately_is_noop(self, solo_gs, quiet_console):
        run_inventory_screen(solo_gs, console=quiet_console, read_key=_keys(["cancel"]))
        assert solo_gs.characters["aldric"].hp == 20
