"""The tool-result envelope contract.

`success` means "the call worked". It is owned by the envelope and must never
be shadowed by a payload field — a failed skill check is a successful call.
"""
from __future__ import annotations

import pytest

from src.dm.context import _compact_tool_exchange
from src.dm.tools import _ok, _normalize_envelope


class TestCheckOutcomeVsCallOutcome:
    def test_failed_check_is_still_a_successful_call(self, dispatcher):
        result = dispatcher.dispatch("ability_check", {
            "character_id": "aldric", "ability": "STR", "skill": "Athletics", "dc": 30,
        })
        assert result["success"] is True     # the call worked
        assert result["passed"] is False     # the roll missed DC 30
        assert "error" not in result

    def test_passed_check(self, dispatcher):
        result = dispatcher.dispatch("ability_check", {
            "character_id": "aldric", "ability": "STR", "skill": "Athletics", "dc": 1,
        })
        assert result["success"] is True
        assert result["passed"] is True

    def test_saving_throw_has_the_same_shape(self, dispatcher):
        result = dispatcher.dispatch("saving_throw", {
            "character_id": "aldric", "ability": "CON", "dc": 30,
        })
        assert result["success"] is True
        assert result["passed"] is False
        assert "error" not in result

    def test_real_errors_still_report_failure(self, dispatcher):
        result = dispatcher.dispatch("ability_check", {
            "character_id": "aldric", "ability": "LUCK", "dc": 10,
        })
        assert result["success"] is False
        assert "LUCK" in result["error"]


class TestEnvelopeHelpers:
    def test_ok_rejects_reserved_keys(self):
        with pytest.raises(ValueError, match="reserved"):
            _ok(success=False, total=3)
        with pytest.raises(ValueError, match="reserved"):
            _ok(error="boom")

    def test_ok_passes_payload_through(self):
        assert _ok(total=7, passed=True) == {"success": True, "total": 7, "passed": True}

    def test_normalize_defaults_missing_success(self):
        assert _normalize_envelope("thing", {"damage": 4})["success"] is True

    def test_normalize_synthesizes_missing_error(self):
        out = _normalize_envelope("thing", {"success": False})
        assert out["error"] == "thing failed."

    def test_normalize_preserves_existing_error(self):
        out = _normalize_envelope("thing", {"success": False, "error": "no slots"})
        assert out["error"] == "no slots"

    def test_normalize_rejects_non_dict(self):
        with pytest.raises(TypeError):
            _normalize_envelope("thing", ["not", "a", "dict"])


class TestEveryResultIsWellFormed:
    """The twelve branches that returned engine dicts verbatim used to arrive
    with no `success` key at all."""

    CALLS = [
        ("roll_dice", {"expression": "1d20"}),
        ("ability_check", {"character_id": "aldric", "ability": "STR", "dc": 10}),
        ("saving_throw", {"character_id": "aldric", "ability": "CON", "dc": 10}),
        ("get_character_sheet", {"character_id": "aldric"}),
        ("apply_damage", {"target_id": "aldric", "amount": 3, "damage_type": "fire"}),
        ("apply_healing", {"target_id": "aldric", "amount": 3}),
        ("apply_condition", {"character_id": "aldric", "condition": "prone"}),
        ("remove_condition", {"character_id": "aldric", "condition": "prone"}),
        ("add_item", {"character_id": "aldric", "item_name": "Rope", "quantity": 1}),
        ("award_xp", {"character_ids": ["aldric"], "amount": 10, "reason": "test"}),
        ("use_second_wind", {"character_id": "aldric"}),
        ("learn_spell", {"character_id": "zara", "spell_name": "Shield"}),
        ("equip_armor", {"character_id": "aldric", "armor_name": "Chain Mail"}),
        ("advance_time", {"hours": 1}),
        ("end_turn", {}),
        ("nonexistent_tool", {}),
    ]

    @pytest.mark.parametrize("tool,inputs", CALLS, ids=[c[0] for c in CALLS])
    def test_result_has_boolean_success(self, dispatcher, tool, inputs):
        result = dispatcher.dispatch(tool, inputs)
        assert isinstance(result, dict)
        assert isinstance(result["success"], bool)

    @pytest.mark.parametrize("tool,inputs", CALLS, ids=[c[0] for c in CALLS])
    def test_failures_always_carry_an_error(self, dispatcher, tool, inputs):
        result = dispatcher.dispatch(tool, inputs)
        if result["success"] is False:
            assert result.get("error"), f"{tool} failed with no error message"


class TestCompaction:
    """A failed check used to compact to the literal string 'FAILED: ?'."""

    def _compact(self, result: dict) -> str:
        import json
        return _compact_tool_exchange(
            [{"type": "tool_use", "id": "t1", "name": "ability_check",
              "input": {"character_id": "aldric", "skill": "Stealth", "dc": 15}}],
            [{"type": "tool_result", "tool_use_id": "t1", "content": json.dumps(result)}],
        )

    def test_failed_check_keeps_its_detail(self):
        out = self._compact({"success": True, "passed": False, "total": 7, "dc": 15})
        assert "FAILED" not in out
        assert "(fail)" in out and "7" in out

    def test_passed_check(self):
        out = self._compact({"success": True, "passed": True, "total": 18, "dc": 15})
        assert "(pass)" in out and "18" in out

    def test_real_error_still_reads_as_failed(self):
        out = self._compact({"success": False, "error": "no such character"})
        assert "FAILED: no such character" in out

    def test_errorless_failure_does_not_render_question_mark(self):
        out = self._compact({"success": False})
        assert out.endswith("FAILED: no error message]")
