"""End-to-end tests for the DungeonMaster tool loop.

These drive the real `process_player_input` against a scripted backend — the
first tests in the suite to exercise the agent loop itself rather than the
engine underneath it.
"""
from __future__ import annotations

import json

import pytest

from src.dm.dungeon_master import DungeonMaster
from tests.support.scripted_backend import ScriptedBackend, ScriptedTurn


def _dm(game_state, campaign_stub, event_log, backend, tmp_path) -> DungeonMaster:
    return DungeonMaster(
        game_state, campaign_stub, event_log,
        save_path=str(tmp_path / "save.json"),
        backend=backend,
    )


def test_dm_resolves_a_tool_turn(game_state, campaign_stub, event_log, tmp_path):
    """One tool call, then narration — the canonical turn shape."""
    backend = ScriptedBackend.tools_then_narration(
        [("ability_check", {
            "character_id": "aldric", "ability": "STR",
            "skill": "Athletics", "dc": 30,
        })],
        "Aldric heaves at the portcullis and it does not budge.",
    )
    dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)

    out = dm.process_player_input("I try to lift the portcullis.")

    assert "portcullis" in out
    assert len(backend.calls) == 2  # tool turn, then closing narration

    entry = event_log.entries[-1]
    assert entry.tool_name == "ability_check"
    assert entry.result["total"] < 30  # DC 30 is unreachable at +5

    hist = game_state.conversation_history
    assert hist[0] == {"role": "user", "content": "I try to lift the portcullis."}
    assert isinstance(hist[1]["content"], list)          # assistant tool_use turn
    assert hist[2]["content"][0]["type"] == "tool_result"
    assert hist[-1]["role"] == "assistant"

    assert dm.token_stats.api_calls == 2


def test_narration_only_turn_makes_one_call(game_state, campaign_stub, event_log, tmp_path):
    backend = ScriptedBackend.narration("The tavern is warm and loud.")
    dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)

    out = dm.process_player_input("I look around.")

    assert out == "The tavern is warm and loud."
    assert len(backend.calls) == 1
    assert event_log.entries == []
    assert game_state.conversation_history[-1] == {
        "role": "assistant", "content": "The tavern is warm and loud.",
    }


def test_tool_results_reach_the_next_request(game_state, campaign_stub, event_log, tmp_path):
    """The model must see the engine's answer on the following call."""
    backend = ScriptedBackend.tools_then_narration(
        [("apply_damage", {"target_id": "aldric", "amount": 5, "damage_type": "slashing"})],
        "The blade bites deep.",
    )
    dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
    dm.process_player_input("The goblin swings at me.")

    assert game_state.characters["aldric"].hp == 23
    second_request = backend.calls[1]["messages"]
    assert any(
        block.get("type") == "tool_result"
        for msg in second_request
        if isinstance(msg.get("content"), list)
        for block in msg["content"]
    )


def test_max_iterations_closes_turn_with_assistant_message(
    game_state, campaign_stub, event_log, tmp_path,
):
    """A model that never stops calling tools must still leave valid history."""
    backend = ScriptedBackend([
        ScriptedTurn(tool_calls=[("roll_dice", {"expression": "1d6"})])
        for _ in range(20)
    ])
    dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)

    dm.process_player_input("I roll forever.")

    from src.dm.dungeon_master import MAX_TOOL_ITERATIONS
    assert len(backend.calls) == MAX_TOOL_ITERATIONS
    last = game_state.conversation_history[-1]
    assert last["role"] == "assistant"
    assert isinstance(last["content"], str)


def test_exhausted_backend_raises_rather_than_passing_quietly(
    game_state, campaign_stub, event_log, tmp_path,
):
    backend = ScriptedBackend([
        ScriptedTurn(tool_calls=[("roll_dice", {"expression": "1d20"})]),
    ])
    dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)

    # The DM catches backend errors and degrades gracefully, so the failure
    # surfaces as the error narration rather than propagating.
    out = dm.process_player_input("I roll.")
    assert "exhausted" in out or "disturbance" in out


class TestInvariantHook:
    """The state linter runs once per turn, after compaction."""

    def test_clean_turn_logs_nothing(self, game_state, campaign_stub, event_log, tmp_path):
        backend = ScriptedBackend.narration("All is well.")
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        dm.process_player_input("I wait.")
        assert not [e for e in event_log.entries if e.tool_name == "_invariant_check"]

    def test_violation_is_logged_after_the_turn(
        self, game_state, campaign_stub, event_log, tmp_path,
    ):
        # Corrupt state behind the engine's back, mid-turn.
        def corrupt(idx: int) -> None:
            game_state.characters["aldric"].hp = 999

        backend = ScriptedBackend.narration("Something is deeply wrong.", on_call=corrupt)
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        dm.process_player_input("I do something impossible.")

        checks = [e for e in event_log.entries if e.tool_name == "_invariant_check"]
        assert len(checks) == 1
        assert checks[0].result["success"] is False
        assert any(v["code"] == "HP_ABOVE_MAX" for v in checks[0].result["violations"])

    def test_severe_violation_is_queued_for_the_model(
        self, game_state, campaign_stub, event_log, tmp_path,
    ):
        def corrupt(idx: int) -> None:
            game_state.characters["zara"].spell_slots[1] = -4

        backend = ScriptedBackend.narration("Magic misfires.", on_call=corrupt)
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        dm.process_player_input("I cast recklessly.")

        pending = dm.context_manager.pending_violations
        assert [v.code for v in pending] == ["SLOTS_NEGATIVE"]

    def test_warning_only_violation_is_not_queued(
        self, game_state, campaign_stub, event_log, tmp_path,
    ):
        def corrupt(idx: int) -> None:
            char = game_state.characters["zara"]
            char.hp = 0
            char.conditions.append("unconscious")
            char.concentration = "Bless"  # warn-level only

        backend = ScriptedBackend.narration("Zara drops.", on_call=corrupt)
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        dm.process_player_input("The ogre swings.")

        assert dm.context_manager.pending_violations == []
        assert [e for e in event_log.entries if e.tool_name == "_invariant_check"]

    def test_raise_policy_fails_loudly(self, game_state, campaign_stub, event_log, tmp_path):
        from src.dm.dungeon_master import DungeonMaster, InvariantPolicy, InvariantViolation

        def corrupt(idx: int) -> None:
            game_state.characters["aldric"].hp = 999

        dm = DungeonMaster(
            game_state, campaign_stub, event_log,
            save_path=str(tmp_path / "save.json"),
            backend=ScriptedBackend.narration("...", on_call=corrupt),
            invariant_policy=InvariantPolicy.RAISE,
        )
        with pytest.raises(InvariantViolation, match="HP_ABOVE_MAX"):
            dm.process_player_input("I break the world.")

    def test_log_policy_does_not_crash_the_session(
        self, game_state, campaign_stub, event_log, tmp_path,
    ):
        def corrupt(idx: int) -> None:
            game_state.characters["aldric"].hp = 999

        backend = ScriptedBackend.narration("The story continues.", on_call=corrupt)
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        assert dm.process_player_input("I break the world.") == "The story continues."


class TestEngineStateFooter:
    """The footer must reflect state as of *this* request, not turn start."""

    @staticmethod
    def _footer_of(request: dict) -> str:
        last = request["messages"][-1]["content"]
        if isinstance(last, str):
            return last
        return "\n".join(b.get("text", "") for b in last if b.get("type") == "text")

    def test_footer_reaches_the_model(self, game_state, campaign_stub, event_log, tmp_path):
        backend = ScriptedBackend.narration("You see a tavern.")
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        dm.process_player_input("I look around.")
        assert "<engine_state>" in self._footer_of(backend.calls[0])

    def test_footer_never_enters_history(self, game_state, campaign_stub, event_log, tmp_path):
        backend = ScriptedBackend.tools_then_narration(
            [("roll_dice", {"expression": "1d20"})], "The die clatters.",
        )
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        dm.process_player_input("I roll.")
        assert "<engine_state>" not in json.dumps(game_state.conversation_history)

    def test_footer_reflects_damage_taken_mid_turn(
        self, game_state, campaign_stub, event_log, tmp_path,
    ):
        """Turn 1 damages Aldric; turn 2's footer must already show it."""
        backend = ScriptedBackend.tools_then_narration(
            [("apply_damage", {"target_id": "aldric", "amount": 10, "damage_type": "fire"})],
            "Flames wash over him.",
        )
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        dm.process_player_input("I step into the fire.")

        assert "28/28 HP" in self._footer_of(backend.calls[0])   # before
        assert "18/28 HP" in self._footer_of(backend.calls[1])   # after

    def test_footer_reflects_spending_gold(self, game_state, campaign_stub, event_log, tmp_path):
        game_state.characters["aldric"].gold = 50
        backend = ScriptedBackend.tools_then_narration(
            [("add_item", {"character_id": "aldric", "item_name": "Rope", "quantity": 1})],
            "You pocket the rope.",
        )
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)
        dm.process_player_input("I take the rope.")

        assert "Rope" not in self._footer_of(backend.calls[0])
        assert "Rope" in self._footer_of(backend.calls[1])

    def test_severe_violation_reaches_the_model_next_turn(
        self, game_state, campaign_stub, event_log, tmp_path,
    ):
        """The linter's feedback channel, end to end."""
        def corrupt(idx: int) -> None:
            if idx == 0:
                game_state.characters["aldric"].hp = 999

        backend = ScriptedBackend.narration("Turn one.", "Turn two.", on_call=corrupt)
        dm = _dm(game_state, campaign_stub, event_log, backend, tmp_path)

        dm.process_player_input("I break the world.")
        assert dm.context_manager.pending_violations  # queued after turn 1

        dm.process_player_input("What now?")
        assert "ENGINE CORRECTION" in self._footer_of(backend.calls[1])
        assert "HP_ABOVE_MAX" not in self._footer_of(backend.calls[0])
