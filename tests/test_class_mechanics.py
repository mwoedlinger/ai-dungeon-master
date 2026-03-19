"""Tests for class mechanics: spell validation, Second Wind, Lay on Hands,
Sneak Attack, and rest resource recovery."""
from __future__ import annotations

import pytest

from src.engine.rest import long_rest, short_rest
from src.engine.rules import use_lay_on_hands, use_second_wind
from src.models.character import AbilityScores, Armor, Character, Weapon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fighter() -> Character:
    return Character(
        id="aldric", name="Aldric", race="Human", class_name="Fighter",
        level=3, xp=900,
        ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
        hp=20, max_hp=28, ac=16, proficiency_bonus=2,
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
        class_resources={"second_wind": 1, "action_surge": 1},
        hit_dice_remaining=3, hit_die_type="d10",
    )


@pytest.fixture
def paladin() -> Character:
    return Character(
        id="elara", name="Elara", race="Human", class_name="Paladin",
        level=5, xp=6500,
        ability_scores=AbilityScores(STR=16, DEX=10, CON=14, INT=10, WIS=12, CHA=16),
        hp=30, max_hp=44, ac=18, proficiency_bonus=3,
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
        shield=True,
        class_resources={"lay_on_hands": 25, "channel_divinity": 1},
        hit_dice_remaining=5, hit_die_type="d10",
    )


@pytest.fixture
def rogue() -> Character:
    return Character(
        id="vex", name="Vex", race="Elf", class_name="Rogue",
        level=5, xp=6500,
        ability_scores=AbilityScores(STR=10, DEX=18, CON=12, INT=14, WIS=12, CHA=10),
        hp=33, max_hp=33, ac=15, proficiency_bonus=3,
        weapons=[
            Weapon(name="Rapier", damage_dice="1d8", damage_type="piercing", properties=["finesse"]),
            Weapon(name="Shortbow", damage_dice="1d6", damage_type="piercing", properties=["ranged"]),
        ],
        armor=Armor(name="Studded Leather", base_ac=12, armor_type="light"),
        class_resources={"sneak_attack_dice": 3},
        hit_dice_remaining=5, hit_die_type="d8",
    )


@pytest.fixture
def wizard() -> Character:
    return Character(
        id="zara", name="Zara", race="Half-Elf", class_name="Wizard",
        level=3, xp=900,
        ability_scores=AbilityScores(STR=8, DEX=14, CON=12, INT=16, WIS=12, CHA=14),
        hp=19, max_hp=19, ac=13, proficiency_bonus=2,
        spellcasting_ability="INT",
        spell_slots={1: 4, 2: 2}, max_spell_slots={1: 4, 2: 2},
        known_spells=["Fire Bolt", "Magic Missile", "Shield", "Fireball"],
        weapons=[Weapon(name="Quarterstaff", damage_dice="1d6", damage_type="bludgeoning")],
        hit_dice_remaining=3, hit_die_type="d6",
    )


@pytest.fixture
def monk() -> Character:
    return Character(
        id="kai", name="Kai", race="Human", class_name="Monk",
        level=5, xp=6500,
        ability_scores=AbilityScores(STR=10, DEX=18, CON=12, INT=10, WIS=16, CHA=8),
        hp=33, max_hp=33, ac=17, proficiency_bonus=3,
        weapons=[Weapon(name="Quarterstaff", damage_dice="1d6", damage_type="bludgeoning")],
        class_resources={"ki": 3, "extra_attack": 1},
        hit_dice_remaining=5, hit_die_type="d8",
    )


@pytest.fixture
def warlock() -> Character:
    return Character(
        id="hex", name="Hex", race="Tiefling", class_name="Warlock",
        level=5, xp=6500,
        ability_scores=AbilityScores(STR=8, DEX=14, CON=14, INT=12, WIS=10, CHA=18),
        hp=38, max_hp=38, ac=13, proficiency_bonus=3,
        spellcasting_ability="CHA",
        spell_slots={3: 1}, max_spell_slots={3: 2},
        known_spells=["Eldritch Blast", "Hex", "Armor of Agathys"],
        weapons=[Weapon(name="Dagger", damage_dice="1d4", damage_type="piercing", properties=["finesse"])],
        armor=Armor(name="Leather Armor", base_ac=11, armor_type="light"),
        hit_dice_remaining=5, hit_die_type="d8",
    )


# ---------------------------------------------------------------------------
# Second Wind
# ---------------------------------------------------------------------------

class TestSecondWind:
    def test_second_wind_heals(self, fighter):
        result = use_second_wind(fighter)
        assert result["success"] is True
        assert result["healed"] > 0
        assert result["hp_now"] > 20
        assert result["remaining_uses"] == 0

    def test_second_wind_capped_at_max_hp(self):
        char = Character(
            id="t", name="T", race="Human", class_name="Fighter",
            level=5,
            ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
            hp=44, max_hp=44, ac=16, proficiency_bonus=3,
            class_resources={"second_wind": 1},
            hit_dice_remaining=5, hit_die_type="d10",
        )
        result = use_second_wind(char)
        assert result["success"] is True
        assert char.hp == 44  # capped at max

    def test_second_wind_no_charges(self, fighter):
        fighter.class_resources["second_wind"] = 0
        result = use_second_wind(fighter)
        assert result["success"] is False
        assert "no Second Wind" in result["error"]

    def test_second_wind_includes_level_bonus(self, fighter):
        # Level 3 fighter: 1d10 + 3
        result = use_second_wind(fighter)
        assert result["level_bonus"] == 3
        # Min heal: 1 + 3 = 4, max: 10 + 3 = 13
        assert 4 <= result["roll"] + result["level_bonus"] <= 13


# ---------------------------------------------------------------------------
# Lay on Hands
# ---------------------------------------------------------------------------

class TestLayOnHands:
    def test_lay_on_hands_heals_target(self, paladin):
        target = Character(
            id="wounded", name="Wounded", race="Human", class_name="Fighter",
            level=3,
            ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
            hp=5, max_hp=28, ac=16, proficiency_bonus=2,
        )
        result = use_lay_on_hands(paladin, target, 10)
        assert result["success"] is True
        assert result["healed"] == 10
        assert target.hp == 15
        assert result["pool_remaining"] == 15

    def test_lay_on_hands_pool_empty(self, paladin):
        paladin.class_resources["lay_on_hands"] = 0
        target = Character(
            id="t", name="T", race="Human", class_name="Fighter", level=1,
            ability_scores=AbilityScores(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            hp=5, max_hp=10, ac=10, proficiency_bonus=2,
        )
        result = use_lay_on_hands(paladin, target, 5)
        assert result["success"] is False
        assert "pool is empty" in result["error"]

    def test_lay_on_hands_exceeds_pool(self, paladin):
        target = Character(
            id="t", name="T", race="Human", class_name="Fighter", level=1,
            ability_scores=AbilityScores(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            hp=5, max_hp=100, ac=10, proficiency_bonus=2,
        )
        result = use_lay_on_hands(paladin, target, 30)
        assert result["success"] is False
        assert "only has 25" in result["error"]

    def test_lay_on_hands_revives_unconscious(self, paladin):
        target = Character(
            id="t", name="T", race="Human", class_name="Fighter", level=1,
            ability_scores=AbilityScores(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            hp=0, max_hp=10, ac=10, proficiency_bonus=2,
            conditions=["unconscious"],
        )
        result = use_lay_on_hands(paladin, target, 5)
        assert result["success"] is True
        assert result["revived"] is True
        assert target.hp == 5
        assert "unconscious" not in target.conditions

    def test_lay_on_hands_invalid_amount(self, paladin):
        result = use_lay_on_hands(paladin, paladin, 0)
        assert result["success"] is False
        assert "positive" in result["error"]


# ---------------------------------------------------------------------------
# Spell-known validation (via ToolDispatcher)
# ---------------------------------------------------------------------------

class TestSpellKnownValidation:
    @pytest.fixture
    def game_state(self, wizard):
        from src.engine.game_state import GameState
        from src.models.world import WorldState, Location
        world = WorldState(
            current_location_id="town",
            locations={"town": Location(id="town", name="Town", description="A town")},
        )
        return GameState(
            player_character_ids=["zara"],
            characters={"zara": wizard},
            world=world,
        )

    @pytest.fixture
    def dispatcher(self, game_state):
        from src.dm.tools import ToolDispatcher
        from src.log.event_log import EventLog
        return ToolDispatcher(game_state, EventLog())

    def test_known_spell_allowed(self, dispatcher):
        result = dispatcher.dispatch("cast_spell", {
            "caster_id": "zara",
            "spell_name": "Magic Missile",
            "spell_level": 1,
            "target_ids": [],
        })
        # Magic Missile is known — should succeed (or fail for other reasons, not "does not know")
        assert "does not know" not in result.get("error", "")

    def test_unknown_spell_rejected(self, dispatcher):
        result = dispatcher.dispatch("cast_spell", {
            "caster_id": "zara",
            "spell_name": "Cure Wounds",
            "spell_level": 1,
            "target_ids": [],
        })
        assert result["success"] is False
        assert "does not know" in result["error"]
        assert "Known spells:" in result["error"]

    def test_case_insensitive_spell_match(self, dispatcher):
        result = dispatcher.dispatch("cast_spell", {
            "caster_id": "zara",
            "spell_name": "magic missile",
            "spell_level": 1,
            "target_ids": [],
        })
        assert "does not know" not in result.get("error", "")

    def test_empty_known_spells_allows_any(self, dispatcher, game_state):
        """Characters with empty known_spells list (e.g. not fully set up) are not blocked."""
        wizard = game_state.get_character("zara")
        wizard.known_spells = []
        result = dispatcher.dispatch("cast_spell", {
            "caster_id": "zara",
            "spell_name": "Cure Wounds",
            "spell_level": 1,
            "target_ids": [],
        })
        # Should not fail with "does not know"
        assert "does not know" not in result.get("error", "")


# ---------------------------------------------------------------------------
# Sneak Attack
# ---------------------------------------------------------------------------

class TestSneakAttack:
    @pytest.fixture
    def game_state(self, rogue):
        from src.engine.game_state import GameState
        from src.models.world import WorldState, Location
        from src.models.monster import Monster, MonsterAction
        goblin = Monster(
            id="goblin_1", name="Goblin", race="Goblin", class_name="monster",
            level=1,
            ability_scores=AbilityScores(STR=8, DEX=14, CON=10, INT=10, WIS=8, CHA=8),
            hp=7, max_hp=7, ac=15, proficiency_bonus=2, is_player=False,
            challenge_rating=0.25, xp_value=50,
            actions=[MonsterAction(name="Scimitar", description="Melee", action_type="action",
                                   attack_bonus=4, damage_dice="1d6", damage_type="slashing")],
            weapons=[Weapon(name="Scimitar", damage_dice="1d6", damage_type="slashing")],
        )
        ally = Character(
            id="ally", name="Ally", race="Human", class_name="Fighter",
            level=3,
            ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
            hp=28, max_hp=28, ac=16, proficiency_bonus=2,
        )
        world = WorldState(
            current_location_id="dungeon",
            locations={"dungeon": Location(id="dungeon", name="Dungeon", description="Dark")},
        )
        return GameState(
            player_character_ids=["vex", "ally"],
            characters={"vex": rogue, "ally": ally, "goblin_1": goblin},
            world=world,
        )

    @pytest.fixture
    def dispatcher(self, game_state):
        from src.dm.tools import ToolDispatcher
        from src.log.event_log import EventLog
        return ToolDispatcher(game_state, EventLog())

    def test_sneak_attack_with_advantage(self, dispatcher, game_state):
        """Sneak Attack triggers with advantage + finesse weapon."""
        # Run attack many times to get a hit
        for _ in range(20):
            game_state.characters["goblin_1"].hp = 50  # keep alive
            result = dispatcher.dispatch("attack", {
                "attacker_id": "vex",
                "target_id": "goblin_1",
                "weapon_name": "Rapier",
                "advantage": True,
            })
            if result.get("hits"):
                assert "sneak_attack" in result
                assert result["sneak_attack"]["dice"] == "3d6"
                assert result["sneak_attack"]["damage"] > 0
                return
        pytest.skip("No hits in 20 attempts")

    def test_sneak_attack_with_ally_nearby(self, dispatcher, game_state):
        """Sneak Attack triggers when ally is in combat (simplified adjacency)."""
        from src.engine import combat as combat_engine
        combat_engine.start_combat(game_state, ["vex", "ally", "goblin_1"])
        # Ensure it's vex's turn for action economy
        game_state.combat.turn_order = ["vex", "ally", "goblin_1"]
        game_state.combat.current_turn_index = 0
        for _ in range(20):
            game_state.characters["goblin_1"].hp = 50
            # Reset action for each attempt
            game_state.combat.combatants["vex"].has_action = True
            result = dispatcher.dispatch("attack", {
                "attacker_id": "vex",
                "target_id": "goblin_1",
                "weapon_name": "Rapier",
            })
            if result.get("hits"):
                assert "sneak_attack" in result
                return
        pytest.skip("No hits in 20 attempts")

    def test_no_sneak_attack_without_finesse_or_ranged(self, dispatcher, game_state, rogue):
        """Non-finesse, non-ranged weapon doesn't trigger Sneak Attack."""
        rogue.weapons.append(
            Weapon(name="Club", damage_dice="1d4", damage_type="bludgeoning")
        )
        for _ in range(20):
            game_state.characters["goblin_1"].hp = 50
            result = dispatcher.dispatch("attack", {
                "attacker_id": "vex",
                "target_id": "goblin_1",
                "weapon_name": "Club",
                "advantage": True,
            })
            if result.get("hits"):
                assert "sneak_attack" not in result
                return
        pytest.skip("No hits in 20 attempts")

    def test_no_sneak_attack_without_advantage_or_ally(self, dispatcher, game_state):
        """No Sneak Attack without advantage and no ally nearby."""
        # Remove ally from player_character_ids
        game_state.player_character_ids = ["vex"]
        for _ in range(20):
            game_state.characters["goblin_1"].hp = 50
            result = dispatcher.dispatch("attack", {
                "attacker_id": "vex",
                "target_id": "goblin_1",
                "weapon_name": "Rapier",
            })
            if result.get("hits"):
                assert "sneak_attack" not in result
                return
        pytest.skip("No hits in 20 attempts")

    def test_sneak_attack_with_ranged_weapon(self, dispatcher, game_state):
        """Sneak Attack works with ranged weapons."""
        for _ in range(20):
            game_state.characters["goblin_1"].hp = 50
            result = dispatcher.dispatch("attack", {
                "attacker_id": "vex",
                "target_id": "goblin_1",
                "weapon_name": "Shortbow",
                "advantage": True,
            })
            if result.get("hits"):
                assert "sneak_attack" in result
                return
        pytest.skip("No hits in 20 attempts")


# ---------------------------------------------------------------------------
# Rest resource recovery
# ---------------------------------------------------------------------------

class TestShortRestResources:
    def test_short_rest_restores_second_wind(self, fighter):
        fighter.class_resources["second_wind"] = 0
        fighter.class_resources["action_surge"] = 0
        result = short_rest(fighter, 0)
        assert result["success"] is True
        assert fighter.class_resources["second_wind"] == 1
        assert fighter.class_resources["action_surge"] == 1
        assert "resources_restored" in result

    def test_short_rest_restores_ki(self, monk):
        monk.class_resources["ki"] = 0
        result = short_rest(monk, 0)
        assert result["success"] is True
        # Monk level 5: ki = level = 5
        assert monk.class_resources["ki"] == 5

    def test_short_rest_does_not_restore_lay_on_hands(self, paladin):
        paladin.class_resources["lay_on_hands"] = 0
        short_rest(paladin, 0)
        # Lay on Hands restores only on long rest
        assert paladin.class_resources["lay_on_hands"] == 0

    def test_short_rest_restores_warlock_slots(self, warlock):
        assert warlock.spell_slots[3] == 1
        result = short_rest(warlock, 0)
        assert result["success"] is True
        assert warlock.spell_slots[3] == 2
        assert result.get("spell_slots_restored") is True

    def test_short_rest_does_not_restore_wizard_slots(self, wizard):
        wizard.spell_slots[1] = 0
        short_rest(wizard, 0)
        assert wizard.spell_slots[1] == 0


class TestLongRestResources:
    def test_long_rest_restores_all_resources(self, fighter):
        fighter.class_resources["second_wind"] = 0
        fighter.class_resources["action_surge"] = 0
        result = long_rest(fighter)
        assert result["success"] is True
        assert fighter.class_resources["second_wind"] == 1
        assert fighter.class_resources["action_surge"] == 1

    def test_long_rest_restores_lay_on_hands(self, paladin):
        paladin.class_resources["lay_on_hands"] = 0
        long_rest(paladin)
        # Paladin level 5: lay_on_hands = level * 5 = 25
        assert paladin.class_resources["lay_on_hands"] == 25

    def test_long_rest_restores_ki(self, monk):
        monk.class_resources["ki"] = 0
        long_rest(monk)
        assert monk.class_resources["ki"] == 5

    def test_long_rest_restores_sneak_attack_dice(self, rogue):
        """Sneak attack dice are a scaling resource, should be maintained."""
        rogue.class_resources["sneak_attack_dice"] = 0
        long_rest(rogue)
        # Level 5 Rogue: (5 + 1) // 2 = 3
        assert rogue.class_resources["sneak_attack_dice"] == 3

    def test_long_rest_restores_spell_slots(self, wizard):
        wizard.spell_slots = {1: 0, 2: 0}
        long_rest(wizard)
        assert wizard.spell_slots == {1: 4, 2: 2}


# ---------------------------------------------------------------------------
# ToolDispatcher integration for Second Wind and Lay on Hands
# ---------------------------------------------------------------------------

class TestClassAbilityTools:
    @pytest.fixture
    def game_state(self, fighter, paladin):
        from src.engine.game_state import GameState
        from src.models.world import WorldState, Location
        wounded = Character(
            id="wounded", name="Wounded", race="Human", class_name="Fighter",
            level=3,
            ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
            hp=5, max_hp=28, ac=16, proficiency_bonus=2,
        )
        world = WorldState(
            current_location_id="town",
            locations={"town": Location(id="town", name="Town", description="A town")},
        )
        return GameState(
            player_character_ids=["aldric", "elara", "wounded"],
            characters={"aldric": fighter, "elara": paladin, "wounded": wounded},
            world=world,
        )

    @pytest.fixture
    def dispatcher(self, game_state):
        from src.dm.tools import ToolDispatcher
        from src.log.event_log import EventLog
        return ToolDispatcher(game_state, EventLog())

    def test_second_wind_via_dispatcher(self, dispatcher, fighter):
        result = dispatcher.dispatch("use_second_wind", {"character_id": "aldric"})
        assert result["success"] is True
        assert fighter.hp > 20

    def test_second_wind_non_fighter_rejected(self, dispatcher):
        result = dispatcher.dispatch("use_second_wind", {"character_id": "elara"})
        assert result["success"] is False
        assert "Fighter" in result["error"]

    def test_lay_on_hands_via_dispatcher(self, dispatcher, paladin, game_state):
        result = dispatcher.dispatch("use_lay_on_hands", {
            "character_id": "elara",
            "target_id": "wounded",
            "amount": 10,
        })
        assert result["success"] is True
        assert result["healed"] == 10
        assert paladin.class_resources["lay_on_hands"] == 15

    def test_lay_on_hands_non_paladin_rejected(self, dispatcher):
        result = dispatcher.dispatch("use_lay_on_hands", {
            "character_id": "aldric",
            "target_id": "wounded",
            "amount": 5,
        })
        assert result["success"] is False
        assert "Paladin" in result["error"]
