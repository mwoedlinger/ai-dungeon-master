"""A9 + E5: dodge/dash/disengage and the turn stall they would cause.

There was no way to take any action other than attacking or casting. Adding
one without also advancing the turn would stall combat: a player who dodges
spends their action, the LLM has nothing further to call, and the same
combatant is prompted forever.
"""
from __future__ import annotations

import pytest

from src.engine.combat import start_combat
from src.engine.turn_driver import CombatTurnDriver


@pytest.fixture
def in_combat(game_state_with_goblins, dispatcher):
    gs = game_state_with_goblins
    start_combat(gs, ["aldric", "goblin_1"])
    gs.combat.turn_order = ["aldric", "goblin_1"]
    gs.combat.current_turn_index = 0
    dispatcher.set_turn_scope("aldric")
    return gs


class TestTakeAction:
    @pytest.mark.parametrize("action", ["dodge", "dash", "disengage", "hide", "ready"])
    def test_actions_are_accepted(self, dispatcher, in_combat, action):
        result = dispatcher.dispatch("take_action", {
            "character_id": "aldric", "action": action,
        })
        assert result["success"] is True
        assert result["action"] == action

    def test_unknown_action_is_rejected(self, dispatcher, in_combat):
        result = dispatcher.dispatch("take_action", {
            "character_id": "aldric", "action": "backflip",
        })
        assert result["success"] is False
        assert "dodge" in result["error"]

    def test_requires_active_combat(self, dispatcher, game_state):
        result = dispatcher.dispatch("take_action", {
            "character_id": "aldric", "action": "dodge",
        })
        assert result["success"] is False

    def test_consumes_the_action(self, dispatcher, in_combat):
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        assert in_combat.combat.combatants["aldric"].has_action is False

    def test_cannot_act_twice(self, dispatcher, in_combat):
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        second = dispatcher.dispatch("take_action", {
            "character_id": "aldric", "action": "dash",
        })
        assert second["success"] is False

    def test_reminds_the_llm_to_end_the_turn(self, dispatcher, in_combat):
        result = dispatcher.dispatch("take_action", {
            "character_id": "aldric", "action": "dodge",
        })
        assert "end_turn" in result["reminder"]


class TestMechanicalEffects:
    def test_dodge_gives_attackers_disadvantage(self, dispatcher, in_combat):
        from src.engine.rules import _condition_modifiers
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        char = in_combat.characters["aldric"]
        assert "dodging" in char.conditions
        assert _condition_modifiers(char)["attacked_disadvantage"] is True

    def test_dash_adds_movement(self, dispatcher, in_combat):
        before = in_combat.combat.combatants["aldric"].movement_remaining
        result = dispatcher.dispatch("take_action", {
            "character_id": "aldric", "action": "dash",
        })
        speed = in_combat.characters["aldric"].speed
        assert result["movement_remaining"] == before + speed

    def test_disengage_blocks_opportunity_attacks(self, dispatcher, in_combat):
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "disengage"})
        dispatcher.set_turn_scope(None)
        result = dispatcher.dispatch("opportunity_attack", {
            "attacker_id": "goblin_1", "target_id": "aldric",
        })
        assert result["success"] is False
        assert "disengage" in result["error"].lower()

    def test_help_targets_the_ally(self, dispatcher, in_combat):
        in_combat.combat.turn_order = ["aldric", "zara", "goblin_1"]
        from src.models.combat import Combatant
        in_combat.combat.combatants["zara"] = Combatant(
            character_id="zara", initiative=5, movement_remaining=30,
        )
        result = dispatcher.dispatch("take_action", {
            "character_id": "aldric", "action": "help", "target_id": "zara",
        })
        assert result["success"] is True
        assert "helped" in in_combat.characters["zara"].conditions
        assert "helped" not in in_combat.characters["aldric"].conditions

    def test_help_without_a_target_is_rejected(self, dispatcher, in_combat):
        result = dispatcher.dispatch("take_action", {
            "character_id": "aldric", "action": "help",
        })
        assert result["success"] is False
        assert "target_id" in result["error"]


class TestDurationExpires:
    def test_dodging_survives_the_enemy_turn(self, dispatcher, in_combat):
        """The whole point of Dodge: it must be up when the enemy attacks."""
        from src.engine.combat import end_turn
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        char = in_combat.characters["aldric"]
        assert "dodging" in char.conditions

        end_turn(in_combat)                       # aldric -> goblin
        assert "dodging" in char.conditions       # still up for the goblin's attack
        end_turn(in_combat)                       # goblin -> aldric
        assert "dodging" in char.conditions

    def test_dodging_eventually_expires(self, dispatcher, in_combat):
        from src.engine.combat import end_turn
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        for _ in range(4):
            end_turn(in_combat)
        assert "dodging" not in in_combat.characters["aldric"].conditions

    def test_condition_and_duration_stay_in_sync(self, dispatcher, in_combat):
        from src.engine.invariants import check_invariants
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        assert check_invariants(in_combat) == []


class TestTurnDoesNotStall:
    """E5: without this, the first dodge freezes the fight."""

    def test_turn_advances_when_nothing_is_left(self, dispatcher, in_combat):
        driver = CombatTurnDriver(in_combat, dispatcher)
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        c = in_combat.combat.combatants["aldric"]
        c.has_bonus_action = False
        c.movement_remaining = 0

        assert driver.finish_player_turn("aldric") is True
        assert in_combat.combat.current_combatant_id != "aldric"

    def test_turn_is_kept_while_a_bonus_action_remains(self, dispatcher, in_combat):
        driver = CombatTurnDriver(in_combat, dispatcher)
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        in_combat.combat.combatants["aldric"].movement_remaining = 0
        assert driver.finish_player_turn("aldric") is False
        assert in_combat.combat.current_combatant_id == "aldric"

    def test_turn_is_kept_while_movement_remains(self, dispatcher, in_combat):
        driver = CombatTurnDriver(in_combat, dispatcher)
        dispatcher.dispatch("take_action", {"character_id": "aldric", "action": "dodge"})
        in_combat.combat.combatants["aldric"].has_bonus_action = False
        assert driver.finish_player_turn("aldric") is False

    def test_does_not_touch_another_combatants_turn(self, dispatcher, in_combat):
        driver = CombatTurnDriver(in_combat, dispatcher)
        assert driver.finish_player_turn("goblin_1") is False


class TestToolAvailability:
    def test_take_action_is_a_core_tool(self):
        """It must survive the small-context tool filter — dodging is basic."""
        from src.dm.tools import get_tool_schemas
        names = {s["name"] for s in get_tool_schemas(8_000)}
        assert "take_action" in names
