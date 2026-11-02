"""Economy fixes: A6 (equipped gear unsellable), B5 (price=0 means free),
B4 (rarity strings the price table does not recognise)."""
from __future__ import annotations

import pytest

from src.engine.economy import get_item_price, normalize_rarity, resolve_price


class TestSellEquippedGear:
    """A6: weapons, armour and shields live outside `inventory`, so scanning
    inventory alone made a character's own sword unsellable."""

    def test_sell_an_equipped_weapon(self, dispatcher, game_state):
        char = game_state.characters["aldric"]
        assert any(w.name == "Longsword" for w in char.weapons)
        result = dispatcher.dispatch("sell_item", {
            "character_id": "aldric", "item_name": "Longsword", "price": 15,
        })
        assert result["success"] is True
        assert result["was_equipped"] is True
        assert result["slot"] == "weapon"
        assert char.gold == 15
        assert not any(w.name == "Longsword" for w in char.weapons)

    def test_selling_armor_lowers_ac(self, dispatcher, game_state):
        char = game_state.characters["aldric"]
        before = char.ac
        result = dispatcher.dispatch("sell_item", {
            "character_id": "aldric", "item_name": "Chain Mail", "price": 75,
        })
        assert result["success"] is True
        assert char.armor is None
        assert char.ac < before
        assert result["new_ac"] == char.ac

    def test_selling_a_shield_lowers_ac(self, dispatcher, game_state):
        from src.engine.rules import recalculate_ac
        char = game_state.characters["aldric"]
        char.shield = True
        char.ac = recalculate_ac(char)
        before = char.ac
        result = dispatcher.dispatch("sell_item", {
            "character_id": "aldric", "item_name": "Shield", "price": 10,
        })
        assert result["success"] is True
        assert char.shield is False
        assert char.ac == before - 2

    def test_attuned_items_must_be_unattuned_first(self, dispatcher, game_state):
        from src.models.character import MagicItem
        char = game_state.characters["aldric"]
        char.attuned_items.append(
            MagicItem(name="Ring of Protection", item_type="ring", requires_attunement=True),
        )
        result = dispatcher.dispatch("sell_item", {
            "character_id": "aldric", "item_name": "Ring of Protection", "price": 100,
        })
        assert result["success"] is False
        assert "unattune" in result["error"].lower()

    def test_inventory_items_still_sell(self, dispatcher, game_state):
        from src.models.character import Item
        char = game_state.characters["aldric"]
        char.inventory.append(Item(name="Rope", quantity=2))
        result = dispatcher.dispatch("sell_item", {
            "character_id": "aldric", "item_name": "Rope", "price": 1, "quantity": 2,
        })
        assert result["success"] is True
        assert result.get("was_equipped") is None

    def test_unknown_item_still_fails(self, dispatcher):
        result = dispatcher.dispatch("sell_item", {
            "character_id": "aldric", "item_name": "Excalibur", "price": 5,
        })
        assert result["success"] is False


class TestPriceIsNotFree:
    """B5: `price` was taken at face value, so 0 transferred goods for nothing."""

    def test_zero_price_falls_back_to_the_table(self, dispatcher, game_state):
        char = game_state.characters["aldric"]
        char.gold = 500
        result = dispatcher.dispatch("buy_item", {
            "character_id": "aldric", "item_name": "Longsword", "price": 0,
        })
        assert result["success"] is True
        assert result["gold_spent"] > 0

    def test_missing_price_falls_back_to_the_table(self, dispatcher, game_state):
        game_state.characters["aldric"].gold = 500
        result = dispatcher.dispatch("buy_item", {
            "character_id": "aldric", "item_name": "Longsword",
        })
        assert result["success"] is True
        assert result["gold_spent"] > 0

    def test_unknown_item_with_no_price_is_refused(self, dispatcher, game_state):
        game_state.characters["aldric"].gold = 500
        result = dispatcher.dispatch("buy_item", {
            "character_id": "aldric", "item_name": "Enchanted Sandwich", "price": 0,
            "rarity": "none",
        })
        assert result["success"] is False
        assert "no price known" in result["error"].lower()

    def test_selling_for_zero_does_not_give_the_item_away(self, dispatcher, game_state):
        char = game_state.characters["aldric"]
        result = dispatcher.dispatch("sell_item", {
            "character_id": "aldric", "item_name": "Longsword", "price": 0,
        })
        assert result["success"] is True
        assert char.gold > 0

    def test_negative_price_is_refused(self):
        price, err = resolve_price("Longsword", -5)
        assert price is None
        assert "negative" in err.lower()

    def test_explicit_price_wins(self):
        assert resolve_price("Longsword", 999) == (999, None)


class TestRarityNormalization:
    """B4: SRD rarity strings the price table did not recognise."""

    @pytest.mark.parametrize("given,expected", [
        ("very rare", "very_rare"),
        ("Very Rare", "very_rare"),
        ("very-rare", "very_rare"),
        ("LEGENDARY", "legendary"),
        ("uncommon", "uncommon"),
    ])
    def test_case_and_separator_variants(self, given, expected):
        assert normalize_rarity(given) == expected

    def test_varies_falls_back_to_the_cheapest_tier(self):
        assert normalize_rarity("Varies") == "common"

    def test_unrecognised_rarity_is_none(self):
        assert normalize_rarity("mythic") is None
        assert normalize_rarity(None) is None

    def test_varies_produces_a_price_rather_than_nothing(self):
        assert get_item_price("Bag of Tricks", "Varies") is not None

    def test_very_rare_is_priced_above_uncommon(self):
        assert get_item_price("Widget", "Very Rare") > get_item_price("Widget", "uncommon")

    def test_known_equipment_ignores_rarity(self):
        assert get_item_price("Longsword", "legendary") == get_item_price("Longsword", "common")
