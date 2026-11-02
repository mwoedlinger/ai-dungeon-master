"""A8: stabilized characters must eventually wake up.

`advance_time` never touched the "stable" condition, so a party that stabilized
after a wipe stayed unconscious forever with no way to continue the campaign.
"""
from __future__ import annotations

from src.engine.time_tracking import advance_time


def _stabilize(char):
    char.hp = 0
    char.conditions.extend(["unconscious", "stable"])
    char.death_saves.successes = 3
    return char


class TestStableWakeUp:
    def test_wakes_at_one_hp_after_an_hour(self, game_state):
        char = _stabilize(game_state.characters["aldric"])
        result = advance_time(game_state.world.time, hours=1, game_state=game_state)

        assert char.hp == 1
        assert "stable" not in char.conditions
        assert "unconscious" not in char.conditions
        assert char.death_saves.successes == 0
        assert result["revived"][0]["character_id"] == "aldric"

    def test_does_not_wake_too_early(self, game_state):
        char = _stabilize(game_state.characters["aldric"])
        result = advance_time(game_state.world.time, minutes=30, game_state=game_state)

        assert char.hp == 0
        assert "stable" in char.conditions
        assert "revived" not in result

    def test_does_not_wake_during_combat(self, game_state):
        char = _stabilize(game_state.characters["aldric"])
        game_state.combat.active = True
        advance_time(game_state.world.time, hours=8, game_state=game_state)
        assert char.hp == 0

    def test_does_not_revive_the_dead(self, game_state):
        char = game_state.characters["aldric"]
        char.hp = 0
        char.conditions.extend(["dead", "stable"])
        advance_time(game_state.world.time, hours=8, game_state=game_state)
        assert char.hp == 0
        assert "dead" in char.conditions

    def test_leaves_healthy_characters_alone(self, game_state):
        advance_time(game_state.world.time, hours=8, game_state=game_state)
        assert game_state.characters["aldric"].hp == 28
        assert game_state.characters["zara"].hp == 19

    def test_wakes_the_whole_party(self, game_state):
        for cid in ("aldric", "zara"):
            _stabilize(game_state.characters[cid])
        result = advance_time(game_state.world.time, hours=8, game_state=game_state)
        assert len(result["revived"]) == 2
        assert all(game_state.characters[c].hp == 1 for c in ("aldric", "zara"))

    def test_revived_state_passes_the_linter(self, game_state):
        from src.engine.invariants import check_invariants
        _stabilize(game_state.characters["aldric"])
        advance_time(game_state.world.time, hours=1, game_state=game_state)
        assert check_invariants(game_state) == []


class TestPartyDownReporting:
    def test_reports_a_total_party_wipe(self, game_state):
        for cid in ("aldric", "zara"):
            char = game_state.characters[cid]
            char.hp = 0
            char.conditions.append("unconscious")
        result = advance_time(game_state.world.time, minutes=10, game_state=game_state)

        assert result["party_down"]["all_down"] is True
        assert set(result["party_down"]["down"]) == {"Aldric", "Zara"}

    def test_silent_when_someone_is_standing(self, game_state):
        char = game_state.characters["aldric"]
        char.hp = 0
        char.conditions.append("unconscious")
        result = advance_time(game_state.world.time, minutes=10, game_state=game_state)
        assert "party_down" not in result

    def test_distinguishes_dead_from_downed(self, game_state):
        game_state.characters["aldric"].hp = 0
        game_state.characters["aldric"].conditions.append("dead")
        game_state.characters["zara"].hp = 0
        game_state.characters["zara"].conditions.append("unconscious")
        result = advance_time(game_state.world.time, minutes=10, game_state=game_state)
        assert result["party_down"]["dead"] == ["Aldric"]
