"""Tests for equipment management: AC recalculation, equip/unequip, shields."""
from __future__ import annotations

import pytest

from src.engine.rules import recalculate_ac
from src.models.character import AbilityScores, Armor, Character, Item, Weapon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fighter() -> Character:
    return Character(
        id="aldric", name="Aldric", race="Human", class_name="Fighter",
        level=3, xp=900,
        ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
        hp=28, max_hp=28, ac=16, proficiency_bonus=2,
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
    )


@pytest.fixture
def monk() -> Character:
    return Character(
        id="kai", name="Kai", race="Human", class_name="Monk",
        level=5, xp=6500,
        ability_scores=AbilityScores(STR=10, DEX=18, CON=12, INT=10, WIS=16, CHA=8),
        hp=33, max_hp=33, ac=17, proficiency_bonus=3,
        weapons=[Weapon(name="Quarterstaff", damage_dice="1d6", damage_type="bludgeoning")],
    )


@pytest.fixture
def barbarian() -> Character:
    return Character(
        id="grog", name="Grog", race="Half-Orc", class_name="Barbarian",
        level=4, xp=2700,
        ability_scores=AbilityScores(STR=18, DEX=14, CON=16, INT=8, WIS=10, CHA=10),
        hp=40, max_hp=40, ac=15, proficiency_bonus=2,
        weapons=[Weapon(name="Greataxe", damage_dice="1d12", damage_type="slashing")],
    )


@pytest.fixture
def rogue() -> Character:
    return Character(
        id="vex", name="Vex", race="Elf", class_name="Rogue",
        level=3, xp=900,
        ability_scores=AbilityScores(STR=10, DEX=16, CON=12, INT=14, WIS=12, CHA=10),
        hp=21, max_hp=21, ac=14, proficiency_bonus=2,
        weapons=[Weapon(name="Rapier", damage_dice="1d8", damage_type="piercing", properties=["finesse"])],
        armor=Armor(name="Leather Armor", base_ac=11, armor_type="light"),
    )


# ---------------------------------------------------------------------------
# recalculate_ac
# ---------------------------------------------------------------------------

class TestRecalculateAC:
    def test_heavy_armor_ignores_dex(self, fighter):
        # Chain Mail base_ac=16, heavy → no DEX mod
        assert recalculate_ac(fighter) == 16

    def test_light_armor_adds_full_dex(self, rogue):
        # Leather base_ac=11, light + DEX mod +3 → 14
        assert recalculate_ac(rogue) == 14

    def test_medium_armor_caps_dex_at_2(self):
        char = Character(
            id="t", name="T", race="Human", class_name="Fighter",
            level=1, ability_scores=AbilityScores(STR=14, DEX=16, CON=12, INT=10, WIS=10, CHA=10),
            hp=10, max_hp=10, ac=0, proficiency_bonus=2,
            armor=Armor(name="Chain Shirt", base_ac=13, armor_type="medium"),
        )
        # base 13 + min(DEX mod +3, 2) = 13 + 2 = 15
        assert recalculate_ac(char) == 15

    def test_monk_unarmored_defense(self, monk):
        # Monk: 10 + DEX(+4) + WIS(+3) = 17
        assert recalculate_ac(monk) == 17

    def test_barbarian_unarmored_defense(self, barbarian):
        # Barbarian: 10 + DEX(+2) + CON(+3) = 15
        assert recalculate_ac(barbarian) == 15

    def test_unarmored_no_class_feature(self):
        char = Character(
            id="t", name="T", race="Human", class_name="Wizard",
            level=1, ability_scores=AbilityScores(STR=8, DEX=14, CON=10, INT=16, WIS=12, CHA=10),
            hp=6, max_hp=6, ac=0, proficiency_bonus=2,
        )
        # 10 + DEX(+2) = 12
        assert recalculate_ac(char) == 12

    def test_shield_adds_2(self, fighter):
        fighter.shield = True
        # Chain Mail 16 + shield 2 = 18
        assert recalculate_ac(fighter) == 18

    def test_shield_with_light_armor(self, rogue):
        rogue.shield = True
        # Leather 11 + DEX(+3) + shield 2 = 16
        assert recalculate_ac(rogue) == 16

    def test_shield_unarmored_monk(self, monk):
        monk.shield = True
        # 10 + DEX(+4) + WIS(+3) + 2 = 19
        assert recalculate_ac(monk) == 19

    def test_armor_removal_recalculates(self, fighter):
        fighter.armor = None
        # Fighter (no special unarmored): 10 + DEX(+1) = 11
        assert recalculate_ac(fighter) == 11

    def test_armor_swap_recalculates(self, fighter):
        fighter.armor = Armor(name="Plate", base_ac=18, armor_type="heavy")
        assert recalculate_ac(fighter) == 18

    def test_dex_improvement_affects_light_armor(self, rogue):
        rogue.ability_scores.DEX = 18  # +4 mod
        # Leather 11 + DEX(+4) = 15
        assert recalculate_ac(rogue) == 15

    def test_dex_improvement_no_effect_heavy_armor(self, fighter):
        fighter.ability_scores.DEX = 20  # +5 mod
        # Chain Mail 16, heavy → still 16
        assert recalculate_ac(fighter) == 16

    def test_wis_improvement_affects_monk(self, monk):
        monk.ability_scores.WIS = 18  # +4 mod
        # 10 + DEX(+4) + WIS(+4) = 18
        assert recalculate_ac(monk) == 18

    def test_con_improvement_affects_barbarian(self, barbarian):
        barbarian.ability_scores.CON = 18  # +4 mod
        # 10 + DEX(+2) + CON(+4) = 16
        assert recalculate_ac(barbarian) == 16


# ---------------------------------------------------------------------------
# Equipment tool dispatch (integration)
# ---------------------------------------------------------------------------

class TestEquipmentTools:
    """Test equip/unequip via ToolDispatcher."""

    @pytest.fixture
    def game_state(self, fighter):
        from src.engine.game_state import GameState
        from src.models.world import WorldState, Location
        world = WorldState(
            current_location_id="town",
            locations={"town": Location(id="town", name="Town", description="A town")},
        )
        return GameState(
            player_character_ids=["aldric"],
            characters={"aldric": fighter},
            world=world,
        )

    @pytest.fixture
    def dispatcher(self, game_state):
        from src.dm.tools import ToolDispatcher
        from src.log.event_log import EventLog
        return ToolDispatcher(game_state, EventLog())

    def test_equip_armor(self, dispatcher, game_state):
        fighter = game_state.get_character("aldric")
        # Add plate armor to inventory
        game_state.add_item("aldric", "Plate Armor")
        result = dispatcher.dispatch("equip_armor", {
            "character_id": "aldric",
            "item_name": "Plate Armor",
            "base_ac": 18,
            "armor_type": "heavy",
            "stealth_disadvantage": True,
            "strength_requirement": 15,
        })
        assert result["success"] is True
        assert result["new_ac"] == 18
        assert fighter.armor.name == "Plate Armor"
        # Old armor returned to inventory
        assert any(it.name == "Chain Mail" for it in fighter.inventory)
        # Plate removed from inventory
        assert not any(it.name == "Plate Armor" for it in fighter.inventory)

    def test_unequip_armor(self, dispatcher, game_state):
        fighter = game_state.get_character("aldric")
        result = dispatcher.dispatch("equip_armor", {
            "character_id": "aldric",
            "item_name": "unequip",
        })
        assert result["success"] is True
        assert fighter.armor is None
        # AC should be 10 + DEX(+1) = 11
        assert fighter.ac == 11
        assert any(it.name == "Chain Mail" for it in fighter.inventory)

    def test_equip_shield(self, dispatcher, game_state):
        fighter = game_state.get_character("aldric")
        assert fighter.ac == 16
        result = dispatcher.dispatch("equip_shield", {
            "character_id": "aldric",
            "equip": True,
        })
        assert result["success"] is True
        assert fighter.shield is True
        assert fighter.ac == 18  # 16 + 2

    def test_unequip_shield(self, dispatcher, game_state):
        fighter = game_state.get_character("aldric")
        fighter.shield = True
        fighter.ac = 18
        result = dispatcher.dispatch("equip_shield", {
            "character_id": "aldric",
            "equip": False,
        })
        assert result["success"] is True
        assert fighter.shield is False
        assert fighter.ac == 16

    def test_equip_weapon(self, dispatcher, game_state):
        fighter = game_state.get_character("aldric")
        game_state.add_item("aldric", "Greataxe")
        result = dispatcher.dispatch("equip_weapon", {
            "character_id": "aldric",
            "weapon_name": "Greataxe",
            "damage_dice": "1d12",
            "damage_type": "slashing",
            "properties": ["heavy", "two-handed"],
        })
        assert result["success"] is True
        assert any(w.name == "Greataxe" for w in fighter.weapons)
        # Removed from inventory
        assert not any(it.name == "Greataxe" for it in fighter.inventory)

    def test_unequip_weapon(self, dispatcher, game_state):
        fighter = game_state.get_character("aldric")
        result = dispatcher.dispatch("unequip_weapon", {
            "character_id": "aldric",
            "weapon_name": "Longsword",
        })
        assert result["success"] is True
        assert not any(w.name == "Longsword" for w in fighter.weapons)
        # Added to inventory
        assert any(it.name == "Longsword" for it in fighter.inventory)

    def test_equip_duplicate_weapon_fails(self, dispatcher, game_state):
        result = dispatcher.dispatch("equip_weapon", {
            "character_id": "aldric",
            "weapon_name": "Longsword",
            "damage_dice": "1d8",
            "damage_type": "slashing",
        })
        assert result["success"] is False
        assert "already" in result["error"]

    def test_unequip_nonexistent_weapon_fails(self, dispatcher, game_state):
        result = dispatcher.dispatch("unequip_weapon", {
            "character_id": "aldric",
            "weapon_name": "Flail",
        })
        assert result["success"] is False
        assert "equipped_weapons" in result

    def test_equip_shield_already_equipped(self, dispatcher, game_state):
        fighter = game_state.get_character("aldric")
        fighter.shield = True
        result = dispatcher.dispatch("equip_shield", {
            "character_id": "aldric",
            "equip": True,
        })
        assert result["success"] is False

    def test_improve_ability_score_updates_ac(self, dispatcher, game_state):
        """ASI that affects DEX should update AC for light armor users."""
        fighter = game_state.get_character("aldric")
        # Switch to light armor so DEX matters
        fighter.armor = Armor(name="Leather", base_ac=11, armor_type="light")
        fighter.ac = recalculate_ac(fighter)  # 11 + 1 = 12
        assert fighter.ac == 12

        result = dispatcher.dispatch("improve_ability_score", {
            "character_id": "aldric",
            "ability": "DEX",
            "increase_by": 2,
        })
        assert result["success"] is True
        assert fighter.ac == 13  # 11 + DEX mod(+2) = 13
        assert "ac_changed" in result
