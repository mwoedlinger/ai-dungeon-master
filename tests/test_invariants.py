"""State linter tests.

Half of these assert a violation fires. The other half — just as important —
assert that legal-but-odd states do NOT fire, because a linter that cries wolf
on the RAW-correct death-save terminal state is worse than no linter.
"""
from __future__ import annotations

import pytest

from src.engine.invariants import (
    ERROR,
    SEVERE_CODES,
    WARN,
    check_invariants,
    repair_invariants,
)
from src.models.character import Item
from src.models.combat import Combatant


def codes(gs) -> set[str]:
    return {v.code for v in check_invariants(gs)}


class TestCleanState:
    def test_fresh_state_is_clean(self, game_state):
        assert check_invariants(game_state) == []

    def test_state_with_monsters_is_clean(self, game_state_with_goblins):
        assert check_invariants(game_state_with_goblins) == []


class TestCharacterInvariants:
    def test_hp_above_max(self, game_state):
        game_state.characters["aldric"].hp = 999
        assert "HP_ABOVE_MAX" in codes(game_state)

    def test_hp_negative(self, game_state):
        game_state.characters["aldric"].hp = -3
        assert "HP_NEGATIVE" in codes(game_state)

    def test_temp_hp_negative(self, game_state):
        game_state.characters["aldric"].temp_hp = -1
        assert "TEMP_HP_NEGATIVE" in codes(game_state)

    def test_gold_negative(self, game_state):
        game_state.characters["aldric"].gold = -5
        assert "GOLD_NEGATIVE" in codes(game_state)

    def test_slots_above_max(self, game_state):
        game_state.characters["zara"].spell_slots[1] = 99
        assert "SLOTS_ABOVE_MAX" in codes(game_state)

    def test_slots_negative(self, game_state):
        game_state.characters["zara"].spell_slots[1] = -1
        assert "SLOTS_NEGATIVE" in codes(game_state)

    def test_zero_quantity_item(self, game_state):
        game_state.characters["aldric"].inventory.append(Item(name="Ghost Rope", quantity=0))
        assert "ITEM_QTY_NONPOSITIVE" in codes(game_state)

    def test_attunement_over_limit(self, game_state):
        from src.models.character import MagicItem
        char = game_state.characters["aldric"]
        char.attuned_items = [
            MagicItem(name=f"Ring {i}", item_type="ring", requires_attunement=True)
            for i in range(4)
        ]
        assert "ATTUNEMENT_OVER_LIMIT" in codes(game_state)


class TestLifeState:
    def test_dead_but_alive(self, game_state):
        char = game_state.characters["aldric"]
        char.conditions.append("dead")
        assert "DEAD_AND_ALIVE" in codes(game_state)

    def test_dead_and_stable(self, game_state):
        char = game_state.characters["aldric"]
        char.hp = 0
        char.conditions.extend(["dead", "stable"])
        assert "DEAD_AND_STABLE" in codes(game_state)

    def test_pc_at_zero_hp_without_unconscious(self, game_state):
        game_state.characters["aldric"].hp = 0
        assert "CONSCIOUS_AT_ZERO_HP" in codes(game_state)

    def test_unconscious_with_hp(self, game_state):
        game_state.characters["aldric"].conditions.append("unconscious")
        assert "UNCONSCIOUS_WITH_HP" in codes(game_state)

    def test_impossible_death_save_count(self, game_state):
        game_state.characters["aldric"].death_saves.failures = 7
        assert "DEATH_SAVE_COUNT_IMPOSSIBLE" in codes(game_state)

    def test_concentration_while_down(self, game_state):
        char = game_state.characters["zara"]
        char.hp = 0
        char.conditions.append("unconscious")
        char.concentration = "Bless"
        assert "CONCENTRATION_ON_UNCONSCIOUS" in codes(game_state)


class TestLegalStatesThatMustNotFire:
    """Each of these is reachable in a correctly-played game."""

    def test_four_death_save_failures_is_legal(self, game_state):
        # A natural 1 adds two failures, so 2 -> 4 is reachable.
        char = game_state.characters["aldric"]
        char.hp = 0
        char.conditions.append("unconscious")
        char.death_saves.failures = 4
        assert "DEATH_SAVE_COUNT_IMPOSSIBLE" not in codes(game_state)

    def test_stable_unconscious_at_zero_hp_is_legal(self, game_state):
        char = game_state.characters["aldric"]
        char.hp = 0
        char.conditions.extend(["unconscious", "stable"])
        char.death_saves.successes = 3
        assert check_invariants(game_state) == []

    def test_dead_pc_at_zero_hp_is_legal(self, game_state):
        char = game_state.characters["aldric"]
        char.hp = 0
        char.conditions.append("dead")
        assert check_invariants(game_state) == []

    def test_downed_monster_during_combat_is_legal(self, game_state_with_goblins):
        gs = game_state_with_goblins
        gs.characters["goblin_1"].hp = 0
        gs.combat.active = True
        gs.combat.round = 1
        gs.combat.turn_order = ["aldric", "goblin_1"]
        gs.combat.combatants = {
            cid: Combatant(character_id=cid, initiative=10, movement_remaining=30)
            for cid in gs.combat.turn_order
        }
        assert check_invariants(gs) == []

    def test_hp_and_max_hp_both_zero_is_not_negative(self, game_state):
        char = game_state.characters["aldric"]
        char.hp = 0
        char.max_hp = 0
        char.conditions.append("dead")
        assert "HP_NEGATIVE" not in codes(game_state)

    def test_indefinite_condition_without_duration_is_legal(self, game_state):
        gs = game_state
        gs.characters["aldric"].conditions.append("cursed")
        gs.combat.active = True
        gs.combat.round = 1
        gs.combat.turn_order = ["aldric"]
        gs.combat.combatants = {
            "aldric": Combatant(character_id="aldric", initiative=10, movement_remaining=30),
        }
        assert "CONDITION_DURATION_DRIFT" not in codes(gs)

    def test_free_form_conditions_are_not_vocabulary_checked(self, game_state):
        game_state.characters["aldric"].conditions.extend(["exhaustion_2", "moonstruck"])
        assert check_invariants(game_state) == []


class TestCombatInvariants:
    def _start(self, gs, order):
        gs.combat.active = True
        gs.combat.round = 1
        gs.combat.turn_order = list(order)
        gs.combat.combatants = {
            cid: Combatant(character_id=cid, initiative=10, movement_remaining=30)
            for cid in order
        }

    def test_out_of_range_turn_index_detected_without_raising(self, game_state_with_goblins):
        gs = game_state_with_goblins
        self._start(gs, ["aldric", "goblin_1"])
        gs.combat.current_turn_index = 5
        # Must not touch CombatState.current_combatant_id, which would IndexError.
        assert "TURN_INDEX_OUT_OF_RANGE" in codes(gs)

    def test_active_combat_with_empty_order(self, game_state):
        game_state.combat.active = True
        assert "COMBAT_ACTIVE_EMPTY_ORDER" in codes(game_state)

    def test_round_not_positive(self, game_state_with_goblins):
        gs = game_state_with_goblins
        self._start(gs, ["aldric", "goblin_1"])
        gs.combat.round = 0
        assert "ROUND_NOT_POSITIVE" in codes(gs)

    def test_turn_order_references_missing_character(self, game_state):
        self._start(game_state, ["aldric", "ghost"])
        assert "TURN_ORDER_MISSING_CHARACTER" in codes(game_state)

    def test_combatant_set_mismatch(self, game_state_with_goblins):
        gs = game_state_with_goblins
        self._start(gs, ["aldric", "goblin_1"])
        del gs.combat.combatants["goblin_1"]
        assert "COMBATANT_SET_MISMATCH" in codes(gs)

    def test_orphan_condition_duration(self, game_state):
        self._start(game_state, ["aldric"])
        game_state.combat.combatants["aldric"].condition_durations = {"poisoned": 2}
        assert "CONDITION_DURATION_DRIFT" in codes(game_state)

    def test_lingering_monster_after_combat(self, game_state_with_goblins):
        gs = game_state_with_goblins
        gs.characters["goblin_1"].hp = 0
        gs.combat.active = False
        assert "MONSTER_LINGERING_AFTER_COMBAT" in codes(gs)


class TestWorldInvariants:
    def test_clock_hour_out_of_range(self, game_state):
        game_state.world.time.hour = 25
        assert "CLOCK_HOUR_OUT_OF_RANGE" in codes(game_state)

    def test_clock_day_not_positive(self, game_state):
        game_state.world.time.day = 0
        assert "CLOCK_DAY_NOT_POSITIVE" in codes(game_state)

    def test_unknown_current_location(self, game_state):
        game_state.world.current_location_id = "atlantis"
        assert "CURRENT_LOCATION_UNKNOWN" in codes(game_state)


class TestReporting:
    def test_errors_sort_before_warnings(self, game_state):
        game_state.characters["aldric"].hp = 999           # error
        game_state.characters["zara"].hp = 0
        game_state.characters["zara"].conditions.append("unconscious")
        game_state.characters["zara"].concentration = "Bless"  # warn
        severities = [v.severity for v in check_invariants(game_state)]
        assert severities == sorted(severities, key=lambda s: s != ERROR)

    def test_severe_codes_are_a_subset_of_real_codes(self, game_state):
        game_state.characters["aldric"].hp = 999
        v = check_invariants(game_state)[0]
        assert v.code in SEVERE_CODES
        assert str(v).startswith("HP_ABOVE_MAX [aldric]")


class TestRepair:
    def test_clamps_hp(self, game_state):
        game_state.characters["aldric"].hp = 999
        fixed = repair_invariants(game_state)
        assert game_state.characters["aldric"].hp == 28
        assert "HP_ABOVE_MAX" in {v.code for v in fixed}
        assert check_invariants(game_state) == []

    def test_clamps_slots_and_gold(self, game_state):
        game_state.characters["zara"].spell_slots[1] = -2
        game_state.characters["aldric"].gold = -10
        repair_invariants(game_state)
        assert game_state.characters["zara"].spell_slots[1] == 0
        assert game_state.characters["aldric"].gold == 0

    def test_drops_zero_quantity_items(self, game_state):
        game_state.characters["aldric"].inventory.append(Item(name="Ghost Rope", quantity=0))
        repair_invariants(game_state)
        assert all(i.quantity > 0 for i in game_state.characters["aldric"].inventory)

    def test_resets_stale_death_saves(self, game_state):
        game_state.characters["aldric"].death_saves.failures = 2
        repair_invariants(game_state)
        assert game_state.characters["aldric"].death_saves.failures == 0

    def test_drops_orphan_durations(self, game_state):
        game_state.combat.active = True
        game_state.combat.round = 1
        game_state.combat.turn_order = ["aldric"]
        game_state.combat.combatants = {
            "aldric": Combatant(character_id="aldric", initiative=10,
                                movement_remaining=30,
                                condition_durations={"poisoned": 2}),
        }
        repair_invariants(game_state)
        assert game_state.combat.combatants["aldric"].condition_durations == {}

    def test_does_not_touch_death_conditions(self, game_state):
        char = game_state.characters["aldric"]
        char.hp = 0
        char.conditions.append("dead")
        repair_invariants(game_state)
        assert "dead" in char.conditions
        assert char.hp == 0


class TestPortedFromDebugAgent:
    """Checks that used to live in scripts/debug_agent/report.py."""

    def _start(self, gs, order):
        gs.combat.active = True
        gs.combat.round = 1
        gs.combat.turn_order = list(order)
        gs.combat.combatants = {
            cid: Combatant(character_id=cid, initiative=10, movement_remaining=30)
            for cid in order
        }

    def test_duplicate_turn_order_entries(self, game_state_with_goblins):
        gs = game_state_with_goblins
        self._start(gs, ["aldric", "goblin_1"])
        gs.combat.turn_order = ["aldric", "goblin_1", "aldric"]
        assert "TURN_ORDER_DUPLICATES" in codes(gs)

    def test_downed_monster_as_current_combatant(self, game_state_with_goblins):
        gs = game_state_with_goblins
        self._start(gs, ["goblin_1", "aldric"])
        gs.characters["goblin_1"].hp = 0
        gs.combat.current_turn_index = 0
        assert "DOWNED_MONSTER_IS_CURRENT" in codes(gs)

    def test_downed_monster_not_current_is_legal(self, game_state_with_goblins):
        gs = game_state_with_goblins
        self._start(gs, ["aldric", "goblin_1"])
        gs.characters["goblin_1"].hp = 0
        gs.combat.current_turn_index = 0  # aldric's turn
        assert "DOWNED_MONSTER_IS_CURRENT" not in codes(gs)

    def test_debug_agent_delegates_to_the_linter(self, game_state):
        from scripts.debug_agent.report import validate_state
        game_state.characters["aldric"].hp = 999
        issues = validate_state(game_state)
        assert any("HP_ABOVE_MAX" in i for i in issues)

    def test_four_failures_no_longer_false_positives_in_debug_agent(self, game_state):
        from scripts.debug_agent.report import validate_state
        char = game_state.characters["aldric"]
        char.hp = 0
        char.conditions.append("unconscious")
        char.death_saves.failures = 4
        assert validate_state(game_state) == []
