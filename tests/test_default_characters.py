"""F1: the shipped pregens.

Both started with no gold and an empty inventory, and the wizard had no weapon
at all — so a new game began with nothing to buy with, nothing to use, and one
character unable to make a basic attack.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.engine.economy import get_item_price
from src.engine.rules import recalculate_ac
from src.models.character import Character

PREGEN_PATH = Path("campaigns/default_characters.json")


def _characters() -> list[Character]:
    data = json.loads(PREGEN_PATH.read_text())
    return [Character.model_validate(c) for c in data["characters"]]


PREGENS = _characters()
IDS = [c.id for c in PREGENS]


@pytest.mark.parametrize("char", PREGENS, ids=IDS)
class TestEveryPregen:
    def test_has_starting_gold(self, char):
        assert char.gold > 0, f"{char.name} starts with no money"

    def test_has_an_inventory(self, char):
        assert char.inventory, f"{char.name} starts with an empty pack"

    def test_can_make_a_weapon_attack(self, char):
        assert char.weapons, f"{char.name} has no weapon"

    def test_every_item_has_a_known_price(self, char):
        """An unpriced item cannot be sold without the LLM inventing a value."""
        unpriced = [i.name for i in char.inventory if get_item_price(i.name, "none") is None]
        assert unpriced == [], f"{char.name} carries unpriced items: {unpriced}"

    def test_item_quantities_are_positive(self, char):
        assert all(i.quantity > 0 for i in char.inventory)

    def test_stored_ac_matches_the_engine(self, char):
        """A stale AC silently changes the moment anything re-equips."""
        assert char.ac == recalculate_ac(char)

    def test_hp_is_coherent(self, char):
        assert 0 < char.hp <= char.max_hp

    def test_passes_the_state_linter(self, char):
        from src.engine.invariants import check_invariants
        from src.engine.game_state import GameState
        from src.models.world import Location, WorldState
        gs = GameState(
            player_character_ids=[char.id],
            characters={char.id: char},
            world=WorldState(
                current_location_id="x",
                locations={"x": Location(id="x", name="X", description="")},
            ),
        )
        assert check_invariants(gs) == []


class TestPartyComposition:
    def test_the_party_can_afford_basic_supplies(self):
        total = sum(c.gold for c in PREGENS)
        assert total >= get_item_price("potion of healing") or total > 50

    def test_someone_carries_a_light_source(self):
        assert any(
            any(i.name.lower() == "torch" for i in c.inventory) for c in PREGENS
        )

    def test_the_caster_has_a_focus(self):
        wizard = next(c for c in PREGENS if c.class_name == "Wizard")
        names = {i.name.lower() for i in wizard.inventory}
        assert names & {"arcane focus", "component pouch"}


class TestConsumablesAreActuallyUsable:
    """A potion whose properties carry no recognised effect key parses as
    ordinary gear and cannot be drunk."""

    def test_every_potion_has_a_mechanical_effect(self):
        from src.models.items import consumable_from_properties
        for char in _characters():
            for item in char.inventory:
                if "potion" in item.name.lower():
                    effect = consumable_from_properties(item.properties)
                    assert effect is not None, f"{char.name}'s {item.name} is inert"
                    assert effect.is_mechanical
