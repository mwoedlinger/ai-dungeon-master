"""A5: rests cost in-game time.

`take_short_rest` and `take_long_rest` called the rest engine and nothing else,
so a party could rest indefinitely without the clock moving — quest deadlines
never approached, and nothing that depends on elapsed time ever fired.
"""
from __future__ import annotations

import pytest


class TestShortRest:
    def test_costs_one_hour(self, dispatcher, game_state):
        before = game_state.world.time.hour
        result = dispatcher.dispatch("take_short_rest", {
            "character_id": "aldric", "hit_dice_to_spend": 1,
        })
        assert result["success"] is True
        assert result["time"]["advanced"] is True
        assert game_state.world.time.hour == before + 1


class TestLongRest:
    def test_costs_eight_hours(self, dispatcher, game_state):
        before = game_state.world.time.hour
        dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        assert game_state.world.time.hour == (before + 8) % 24

    def test_crosses_midnight_correctly(self, dispatcher, game_state):
        game_state.world.time.hour = 22
        dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        assert game_state.world.time.day == 2
        assert game_state.world.time.hour == 6

    def test_restores_resources(self, dispatcher, game_state):
        char = game_state.characters["aldric"]
        char.hp = 4
        dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        assert char.hp == char.max_hp


class TestPartyRestAdvancesOnce:
    """The tools are per-character; the clock is not."""

    def test_two_characters_resting_costs_eight_hours_not_sixteen(
        self, dispatcher, game_state,
    ):
        before = game_state.world.time.hour
        first = dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        second = dispatcher.dispatch("take_long_rest", {"character_id": "zara"})

        assert first["time"]["advanced"] is True
        assert second["time"]["advanced"] is False
        assert game_state.world.time.hour == (before + 8) % 24

    def test_a_later_rest_does_advance_again(self, dispatcher, game_state):
        dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        dispatcher.dispatch("advance_time", {"hours": 6})
        result = dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        assert result["time"]["advanced"] is True

    def test_short_and_long_rests_are_tracked_separately(self, dispatcher, game_state):
        dispatcher.dispatch("take_short_rest", {
            "character_id": "aldric", "hit_dice_to_spend": 0,
        })
        result = dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        assert result["time"]["advanced"] is True


class TestCombatGuard:
    @pytest.mark.parametrize("tool,extra", [
        ("take_short_rest", {"hit_dice_to_spend": 1}),
        ("take_long_rest", {}),
    ])
    def test_rest_in_combat_does_not_move_the_clock(
        self, dispatcher, game_state, tool, extra,
    ):
        game_state.combat.active = True
        before = (game_state.world.time.day, game_state.world.time.hour)
        result = dispatcher.dispatch(tool, {"character_id": "aldric", **extra})
        assert result["success"] is False
        assert (game_state.world.time.day, game_state.world.time.hour) == before


class TestKnockOnEffects:
    def test_a_long_rest_can_expire_a_quest_deadline(self, dispatcher, game_state):
        from src.models.world import Quest
        game_state.world.quests.append(Quest(
            id="q1", title="Stop the ritual", description="Before dawn.",
            status="active", deadline_day=1,
        ))
        game_state.world.time.hour = 20
        result = dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        assert result["time"].get("expired_quests")
        assert game_state.world.quests[0].status == "failed"

    def test_a_long_rest_wakes_a_stabilized_ally(self, dispatcher, game_state):
        zara = game_state.characters["zara"]
        zara.hp = 0
        zara.conditions.extend(["unconscious", "stable"])
        dispatcher.dispatch("take_long_rest", {"character_id": "aldric"})
        assert zara.hp == 1
        assert "unconscious" not in zara.conditions

    def test_schemas_state_the_time_cost(self):
        from src.dm.tools import ALL_TOOL_SCHEMAS
        by_name = {s["name"]: s for s in ALL_TOOL_SCHEMAS}
        assert "1 hour" in by_name["take_short_rest"]["description"]
        assert "8 hours" in by_name["take_long_rest"]["description"]
