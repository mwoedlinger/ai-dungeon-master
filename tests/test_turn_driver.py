"""Shared combat turn driver.

The reason this module exists: the CLI and the web server each had their own
copy of this sequence, and the web copy skipped downed PCs outright — so a
dying character never rolled a death save and combat could not end. These
tests pin the behaviour in one place for both front ends.
"""
from __future__ import annotations

import pytest

from src.engine.combat import start_combat
from src.engine.turn_driver import (
    AutoSkipped,
    AwaitPlayerInput,
    CombatEnded,
    CombatTurnDriver,
    DeathSaveResolved,
    MonsterTurn,
    TurnLimitReached,
)


@pytest.fixture
def driver(game_state_with_goblins, dispatcher):
    return CombatTurnDriver(game_state_with_goblins, dispatcher)


def _begin(gs, order):
    start_combat(gs, list(order))
    gs.combat.turn_order = list(order)   # deterministic order for assertions
    gs.combat.current_turn_index = 0


class TestBasicSequencing:
    def test_inactive_combat_ends(self, driver):
        assert isinstance(driver.next_turn(), CombatEnded)

    def test_player_turn_awaits_input(self, game_state_with_goblins, driver):
        _begin(game_state_with_goblins, ["aldric", "goblin_1"])
        outcome = driver.next_turn()
        assert isinstance(outcome, AwaitPlayerInput)
        assert outcome.character_id == "aldric"

    def test_monster_turn_returns_a_prompt(self, game_state_with_goblins, driver):
        _begin(game_state_with_goblins, ["goblin_1", "aldric"])
        outcome = driver.next_turn()
        assert isinstance(outcome, MonsterTurn)
        assert "get_monster_actions('goblin_1')" in outcome.prompt

    def test_monster_turn_sets_turn_scope(self, game_state_with_goblins, driver, dispatcher):
        _begin(game_state_with_goblins, ["goblin_1", "aldric"])
        driver.next_turn()
        assert dispatcher._turn_scope == "goblin_1"

    def test_defeated_monster_is_skipped(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["goblin_1", "aldric"])
        gs.characters["goblin_1"].hp = 0
        outcome = driver.next_turn()
        assert isinstance(outcome, AutoSkipped)
        assert outcome.reason == "defeated"

    def test_dead_character_is_skipped(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["aldric", "goblin_1"])
        gs.characters["aldric"].hp = 0
        gs.characters["aldric"].conditions.append("dead")
        outcome = driver.next_turn()
        assert isinstance(outcome, AutoSkipped)
        assert outcome.reason == "dead"

    def test_missing_combatant_is_skipped(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["aldric", "goblin_1"])
        gs.combat.turn_order[0] = "ghost"
        outcome = driver.next_turn()
        assert isinstance(outcome, AutoSkipped)
        assert "no longer exists" in outcome.reason


class TestDyingPlayer:
    """A7: a downed PC takes their turn to roll a death save."""

    def _down(self, gs, cid="aldric"):
        char = gs.characters[cid]
        char.hp = 0
        char.conditions.append("unconscious")
        return char

    def test_downed_pc_rolls_a_death_save(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["aldric", "goblin_1"])
        char = self._down(gs)
        outcome = driver.next_turn()
        assert isinstance(outcome, DeathSaveResolved)
        assert char.death_saves.successes + char.death_saves.failures > 0

    def test_downed_pc_is_not_skipped_like_a_monster(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["aldric", "goblin_1"])
        self._down(gs)
        assert not isinstance(driver.next_turn(), AutoSkipped)

    def test_death_save_advances_the_turn(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["aldric", "goblin_1"])
        self._down(gs)
        driver.next_turn()
        assert gs.combat.current_combatant_id != "aldric"

    def test_stable_pc_is_skipped_without_rolling(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["aldric", "goblin_1"])
        char = self._down(gs)
        char.conditions.append("stable")
        outcome = driver.next_turn()
        assert outcome.kind == "stable_skip"
        assert char.death_saves.failures == 0

    def test_three_failures_kills(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["aldric"])
        char = self._down(gs)
        char.death_saves.failures = 2
        import src.engine.combat as combat_mod
        from src.models.combat import DiceResult
        # Force a failing roll.
        original = combat_mod.roll_dice
        combat_mod.roll_dice = lambda *a, **k: DiceResult(
            expression="1d20", individual_rolls=[3], modifier=0, total=3,
        )
        try:
            outcome = driver.next_turn()
        finally:
            combat_mod.roll_dice = original
        assert outcome.kind == "died"
        assert "dead" in char.conditions


class TestStuckTurns:
    def test_finish_monster_turn_forces_advance(self, game_state_with_goblins, driver):
        gs = game_state_with_goblins
        _begin(gs, ["goblin_1", "aldric"])
        assert driver.finish_monster_turn("goblin_1") is True
        assert gs.combat.current_combatant_id != "goblin_1"

    def test_finish_monster_turn_is_a_noop_when_turn_advanced(
        self, game_state_with_goblins, driver,
    ):
        gs = game_state_with_goblins
        _begin(gs, ["goblin_1", "aldric"])
        driver.dispatcher.set_turn_scope("goblin_1")
        driver.dispatcher.dispatch("end_turn", {})
        assert driver.finish_monster_turn("goblin_1") is False

    def test_auto_turn_cap_stops_an_unbounded_loop(self, game_state_with_goblins, dispatcher):
        gs = game_state_with_goblins
        driver = CombatTurnDriver(gs, dispatcher, max_auto_turns=5)
        _begin(gs, ["goblin_1", "goblin_2"])
        # Two monsters and no player: without a cap this never terminates.
        for _ in range(5):
            assert isinstance(driver.next_turn(), MonsterTurn)
        assert isinstance(driver.next_turn(), TurnLimitReached)

    def test_cap_resets_when_a_player_acts(self, game_state_with_goblins, dispatcher):
        gs = game_state_with_goblins
        driver = CombatTurnDriver(gs, dispatcher, max_auto_turns=3)
        _begin(gs, ["goblin_1", "aldric"])
        assert isinstance(driver.next_turn(), MonsterTurn)
        driver.finish_monster_turn("goblin_1")
        assert isinstance(driver.next_turn(), AwaitPlayerInput)
        assert driver._auto_turns == 0


class TestPartyWipeTerminates:
    """The softlock this whole phase exists to fix.

    A downed PC, a live enemy, and an LLM that never calls end_turn — the web
    driver previously skipped the PC's turn entirely, so death saves never
    rolled and the fight ran forever.
    """

    def test_downed_pc_reaches_a_terminal_state(self, game_state_with_goblins, dispatcher):
        gs = game_state_with_goblins
        driver = CombatTurnDriver(gs, dispatcher, max_auto_turns=200)
        _begin(gs, ["aldric", "goblin_1"])
        char = gs.characters["aldric"]
        char.hp = 0
        char.conditions.append("unconscious")
        gs.player_character_ids = ["aldric"]  # solo PC: no ally to revive them

        saves_rolled = 0
        for _ in range(200):
            outcome = driver.next_turn()
            if isinstance(outcome, (CombatEnded, TurnLimitReached)):
                break
            if isinstance(outcome, DeathSaveResolved):
                saves_rolled += 1
            if isinstance(outcome, MonsterTurn):
                # Simulate the LLM narrating without ending the turn.
                driver.finish_monster_turn(outcome.character_id)
            if isinstance(outcome, AwaitPlayerInput):
                # A natural 20 revived them; the driver is now correctly
                # waiting on the UI, which this loop cannot supply.
                break
            if {"dead", "stable"} & set(char.conditions):
                break
        else:
            pytest.fail("combat never terminated")

        assert saves_rolled >= 1
        # Every legitimate exit: died, stabilized, or a nat-20 revival.
        resolved = bool({"dead", "stable"} & set(char.conditions)) or char.hp > 0
        assert resolved, (
            f"PC stuck at {char.death_saves.successes}/{char.death_saves.failures} "
            "death saves — this is the softlock"
        )

    def test_stable_pc_with_live_enemy_ends_combat(
        self, game_state_with_goblins, dispatcher,
    ):
        """Every PC stabilized and none can act — the party has lost.

        This used to grind through monster turns forever. It now terminates
        through the rules (`party_defeated`) rather than via the backstop cap.
        """
        gs = game_state_with_goblins
        driver = CombatTurnDriver(gs, dispatcher, max_auto_turns=20)
        _begin(gs, ["aldric", "goblin_1"])
        gs.player_character_ids = ["aldric"]
        char = gs.characters["aldric"]
        char.hp = 0
        char.conditions.extend(["unconscious", "stable"])

        outcomes = []
        for _ in range(50):
            outcome = driver.next_turn()
            outcomes.append(outcome)
            if isinstance(outcome, MonsterTurn):
                driver.finish_monster_turn(outcome.character_id)
            if isinstance(outcome, (CombatEnded, TurnLimitReached)):
                break
        else:
            pytest.fail("loop did not terminate")

        assert isinstance(outcomes[-1], CombatEnded)
        assert not any(isinstance(o, TurnLimitReached) for o in outcomes)
        # Resolved in a couple of turns, not by grinding to the cap.
        assert len(outcomes) < 6

    def test_party_defeated_ends_combat_in_the_engine(self, game_state_with_goblins):
        from src.engine.combat import end_turn
        gs = game_state_with_goblins
        _begin(gs, ["aldric", "goblin_1"])
        gs.player_character_ids = ["aldric"]
        char = gs.characters["aldric"]
        char.hp = 0
        char.conditions.extend(["unconscious", "stable"])

        result = end_turn(gs)
        assert result["combat_over"] is True
        assert result["reason"] == "party_defeated"
        assert gs.combat.active is False

    def test_dying_pc_does_not_end_combat_early(self, game_state_with_goblins):
        """A PC still rolling death saves keeps the fight alive."""
        from src.engine.combat import end_turn
        gs = game_state_with_goblins
        _begin(gs, ["aldric", "goblin_1"])
        gs.player_character_ids = ["aldric"]
        char = gs.characters["aldric"]
        char.hp = 0
        char.conditions.append("unconscious")  # dying, not stable

        result = end_turn(gs)
        assert result.get("reason") != "party_defeated"
        assert gs.combat.active is True
