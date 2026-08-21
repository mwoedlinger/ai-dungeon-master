"""Item view/DTO layer (docs/DESIGN_INVENTORY_UI.md)."""
from __future__ import annotations

from src.models.items import (
    MAX_ATTUNEMENT,
    ConsumableEffect,
    ItemCategory,
    Slot,
    consumable_from_properties,
)


class TestEnums:
    def test_categories_and_slots_exist(self):
        assert ItemCategory.CONSUMABLE.value == "consumable"
        assert {s.value for s in Slot} == {"main_hand", "off_hand", "armor", "attunement"}
        assert MAX_ATTUNEMENT == 3


class TestConsumableEffect:
    def test_mechanical_flag(self):
        assert ConsumableEffect(heal="2d4+2").is_mechanical
        assert ConsumableEffect(cast_spell="Fire Bolt").is_mechanical
        assert not ConsumableEffect(note="tastes of elderberries").is_mechanical

    def test_parse_from_properties_heal(self):
        eff = consumable_from_properties({"heal": "2d4+2"})
        assert eff is not None and eff.heal == "2d4+2"

    def test_parse_from_properties_cast(self):
        eff = consumable_from_properties({"cast_spell": "Fireball", "note": "scroll"})
        assert eff is not None and eff.cast_spell == "Fireball" and eff.note == "scroll"

    def test_non_consumable_returns_none(self):
        assert consumable_from_properties({}) is None
        assert consumable_from_properties({"color": "blue"}) is None
        assert consumable_from_properties(None) is None
