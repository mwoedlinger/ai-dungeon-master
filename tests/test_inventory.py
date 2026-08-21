"""InventoryController — façade over legacy storage (Phase 1)."""
from __future__ import annotations

import pytest

from src.engine.game_state import GameState
from src.engine.inventory import InventoryController, ItemAction
from src.models.character import AbilityScores, Armor, Character, Item, Weapon
from src.models.world import WorldState


def _pc(cid: str, name: str, **over) -> Character:
    base = dict(
        id=cid, name=name, race="Human", class_name="Fighter",
        ability_scores=AbilityScores(STR=14, DEX=12, CON=12, INT=10, WIS=10, CHA=10),
        hp=20, max_hp=30, ac=16, proficiency_bonus=2,
    )
    base.update(over)
    return Character(**base)


@pytest.fixture
def gs() -> GameState:
    aldric = _pc(
        "aldric", "Aldric", gold=47,
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
        inventory=[
            Item(name="Healing Potion", quantity=3, weight=0.5, properties={"heal": "2d4+2"}),
            Item(name="Torch", quantity=5, weight=1.0),
        ],
    )
    mara = _pc("mara", "Mara")
    world = WorldState(current_location_id="loc", locations={})
    return GameState(player_character_ids=["aldric", "mara"],
                     characters={"aldric": aldric, "mara": mara}, world=world)


@pytest.fixture
def ctrl(gs) -> InventoryController:
    return InventoryController(gs)


class TestView:
    def test_reports_gold_weight_capacity_slots(self, ctrl):
        view = ctrl.view("aldric")
        assert view.gold == 47
        # inventory weight only (legacy encumbrance): 3*0.5 + 5*1.0 = 6.5
        assert view.carry_weight == pytest.approx(6.5)
        assert view.capacity == 210.0  # STR 14 * 15
        assert view.encumbrance_tier == "normal"
        slots = {s.slot.value: s.item_name for s in view.slots}
        assert slots["main_hand"] == "Longsword"
        assert slots["armor"] == "Chain Mail"
        assert slots["off_hand"] is None  # no shield

    def test_lists_all_containers_with_equipped_flags(self, ctrl):
        view = ctrl.view("aldric")
        by_name = {i.name: i for i in view.items}
        assert by_name["Longsword"].equipped and by_name["Chain Mail"].equipped
        assert not by_name["Healing Potion"].equipped
        assert by_name["Healing Potion"].category.value == "consumable"
        assert by_name["Torch"].category.value == "gear"


class TestContextualActions:
    def test_potion_offers_use_not_unequip(self, ctrl):
        acts = ctrl.actions_for("aldric", "i:healing potion")
        assert ItemAction.USE in acts and ItemAction.UNEQUIP not in acts
        assert ItemAction.SPLIT in acts  # qty 3

    def test_weapon_offers_unequip_and_give(self, ctrl):
        acts = ctrl.actions_for("aldric", "w:longsword")
        assert ItemAction.UNEQUIP in acts and ItemAction.GIVE in acts
        assert ItemAction.USE not in acts

    def test_armor_offers_unequip_only(self, ctrl):
        acts = ctrl.actions_for("aldric", "a:chain mail")
        assert acts == [ItemAction.EXAMINE, ItemAction.UNEQUIP]

    def test_give_absent_without_second_pc(self, gs):
        gs.player_character_ids = ["aldric"]
        acts = InventoryController(gs).actions_for("aldric", "i:torch")
        assert ItemAction.GIVE not in acts

    def test_reject_invalid_action(self, ctrl):
        res = ctrl.apply("aldric", ItemAction.USE, "w:longsword")
        assert not res.success


class TestUse:
    def test_use_potion_heals_and_decrements(self, ctrl, gs):
        aldric = gs.characters["aldric"]
        res = ctrl.apply("aldric", ItemAction.USE, "i:healing potion")
        assert res.success and aldric.hp > 20
        potion = next(it for it in aldric.inventory if it.name == "Healing Potion")
        assert potion.quantity == 2 and res.data["remaining"] == 2

    def test_use_last_potion_removes_it(self, ctrl, gs):
        aldric = gs.characters["aldric"]
        next(it for it in aldric.inventory if it.name == "Healing Potion").quantity = 1
        ctrl.apply("aldric", ItemAction.USE, "i:healing potion")
        assert not any(it.name == "Healing Potion" for it in aldric.inventory)


class TestUnequip:
    def test_unequip_weapon_moves_to_inventory(self, ctrl, gs):
        aldric = gs.characters["aldric"]
        res = ctrl.apply("aldric", ItemAction.UNEQUIP, "w:longsword")
        assert res.success
        assert not any(w.name == "Longsword" for w in aldric.weapons)
        assert any(it.name == "Longsword" for it in aldric.inventory)

    def test_unequip_armor_recalculates_ac(self, ctrl, gs):
        aldric = gs.characters["aldric"]
        res = ctrl.apply("aldric", ItemAction.UNEQUIP, "a:chain mail")
        assert res.success and aldric.armor is None
        # Fighter, no armor: 10 + DEX(+1) = 11
        assert aldric.ac == 11 and res.data["new_ac"] == 11
        assert any(it.name == "Chain Mail" for it in aldric.inventory)


class TestGiveDrop:
    def test_give_inventory_item_preserves_effect(self, ctrl, gs):
        res = ctrl.apply("aldric", ItemAction.GIVE, "i:healing potion", quantity=2)
        assert res.success and res.data["to"] == "mara"
        giver = next(it for it in gs.characters["aldric"].inventory if it.name == "Healing Potion")
        recv = next(it for it in gs.characters["mara"].inventory if it.name == "Healing Potion")
        assert giver.quantity == 1 and recv.quantity == 2
        assert recv.properties.get("heal") == "2d4+2"  # effect survived the transfer

    def test_give_weapon_moves_to_recipient(self, ctrl, gs):
        ctrl.apply("aldric", ItemAction.GIVE, "w:longsword", to_id="mara")
        assert not any(w.name == "Longsword" for w in gs.characters["aldric"].weapons)
        assert any(w.name == "Longsword" for w in gs.characters["mara"].weapons)

    def test_drop_removes(self, ctrl, gs):
        res = ctrl.apply("aldric", ItemAction.DROP, "i:torch", quantity=5)
        assert res.success
        assert not any(it.name == "Torch" for it in gs.characters["aldric"].inventory)
