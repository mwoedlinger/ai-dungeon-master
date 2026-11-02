"""C1: use / give / drop item tools.

The LLM could add and remove items but had no way to *use* one — a healing
potion in the pack was unreachable except by narrating it, which meant the
engine never applied the healing.
"""
from __future__ import annotations

import pytest

from src.models.character import Item


@pytest.fixture
def with_potion(game_state):
    game_state.characters["aldric"].inventory.append(
        Item(name="Potion of Healing", quantity=2, weight=0.5,
             properties={"heal": "2d4+2"}),
    )
    return game_state


class TestUseItem:
    def test_drinking_a_potion_heals(self, dispatcher, with_potion):
        char = with_potion.characters["aldric"]
        char.hp = 10
        result = dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "Potion of Healing",
        })
        assert result["success"] is True
        assert char.hp > 10

    def test_consumes_one_from_the_stack(self, dispatcher, with_potion):
        with_potion.characters["aldric"].hp = 10
        result = dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "Potion of Healing",
        })
        assert result["remaining"] == 1

    def test_matches_case_insensitively(self, dispatcher, with_potion):
        with_potion.characters["aldric"].hp = 10
        result = dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "potion of healing",
        })
        assert result["success"] is True

    def test_unknown_item_lists_what_is_carried(self, dispatcher, game_state):
        result = dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "Elixir of Nonsense",
        })
        assert result["success"] is False
        assert "Carrying:" in result["error"]

    def test_non_consumable_cannot_be_used(self, dispatcher, game_state):
        game_state.characters["aldric"].inventory.append(Item(name="Rope", quantity=1))
        result = dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "Rope",
        })
        assert result["success"] is False

    def test_healing_never_exceeds_max(self, dispatcher, with_potion):
        char = with_potion.characters["aldric"]
        char.hp = char.max_hp - 1
        dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "Potion of Healing",
        })
        assert char.hp == char.max_hp


class TestCombatActionCost:
    def test_drinking_costs_an_action_in_combat(self, dispatcher, with_potion):
        from src.engine.combat import start_combat
        gs = with_potion
        gs.characters["aldric"].hp = 10
        start_combat(gs, ["aldric"])
        gs.combat.turn_order = ["aldric"]
        gs.combat.current_turn_index = 0
        dispatcher.set_turn_scope("aldric")

        dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "Potion of Healing",
        })
        assert gs.combat.combatants["aldric"].has_action is False

    def test_cannot_drink_twice_in_one_turn(self, dispatcher, with_potion):
        from src.engine.combat import start_combat
        gs = with_potion
        gs.characters["aldric"].hp = 5
        start_combat(gs, ["aldric"])
        gs.combat.turn_order = ["aldric"]
        gs.combat.current_turn_index = 0
        dispatcher.set_turn_scope("aldric")

        dispatcher.dispatch("use_item", {"character_id": "aldric", "item_name": "Potion of Healing"})
        second = dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "Potion of Healing",
        })
        assert second["success"] is False
        assert "action" in second["error"].lower()


class TestGiveItem:
    def test_transfers_between_characters(self, dispatcher, with_potion):
        result = dispatcher.dispatch("give_item", {
            "character_id": "aldric", "to_id": "zara",
            "item_name": "Potion of Healing", "quantity": 1,
        })
        assert result["success"] is True
        zara = with_potion.characters["zara"]
        assert any(i.name == "Potion of Healing" for i in zara.inventory)

    def test_giver_loses_the_item(self, dispatcher, with_potion):
        dispatcher.dispatch("give_item", {
            "character_id": "aldric", "to_id": "zara",
            "item_name": "Potion of Healing", "quantity": 2,
        })
        aldric = with_potion.characters["aldric"]
        assert not any(i.name == "Potion of Healing" for i in aldric.inventory)


class TestDropItem:
    def test_drops_the_whole_stack_by_default(self, dispatcher, with_potion):
        result = dispatcher.dispatch("drop_item", {
            "character_id": "aldric", "item_name": "Potion of Healing",
        })
        assert result["success"] is True
        assert result["dropped"] == 2

    def test_drops_a_partial_stack(self, dispatcher, with_potion):
        dispatcher.dispatch("drop_item", {
            "character_id": "aldric", "item_name": "Potion of Healing", "quantity": 1,
        })
        char = with_potion.characters["aldric"]
        remaining = next(i for i in char.inventory if i.name == "Potion of Healing")
        assert remaining.quantity == 1

    def test_dropping_leaves_no_zero_quantity_ghost(self, dispatcher, with_potion):
        from src.engine.invariants import check_invariants
        dispatcher.dispatch("drop_item", {
            "character_id": "aldric", "item_name": "Potion of Healing",
        })
        assert check_invariants(with_potion) == []


class TestPregensCanUseTheirKit:
    """The shipped party now starts with usable potions (F1)."""

    def test_aldric_can_drink_his_starting_potion(self, dispatcher, game_state):
        import json
        from pathlib import Path
        from src.models.character import Character

        data = json.loads(Path("campaigns/default_characters.json").read_text())
        aldric = Character.model_validate(
            next(c for c in data["characters"] if c["id"] == "aldric"),
        )
        aldric.hp = 5
        game_state.characters["aldric"] = aldric

        result = dispatcher.dispatch("use_item", {
            "character_id": "aldric", "item_name": "Potion of healing",
        })
        assert result["success"] is True, result.get("error")
        assert aldric.hp > 5
