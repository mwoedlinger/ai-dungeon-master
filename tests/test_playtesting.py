"""Tests for playtesting fixes (Task 6)."""
from __future__ import annotations

import pytest

from src.engine.rules import apply_damage
from src.models.character import AbilityScores, Character


def _make_char(**overrides) -> Character:
    defaults = dict(
        id="test", name="Test", race="Human", class_name="Fighter",
        level=3, xp=0,
        ability_scores=AbilityScores(STR=16, DEX=14, CON=14, INT=10, WIS=12, CHA=10),
        hp=30, max_hp=30, ac=16, proficiency_bonus=2,
        saving_throw_proficiencies=["STR", "CON"],
        hit_dice_remaining=3, hit_die_type="d10",
    )
    defaults.update(overrides)
    return Character(**defaults)


class TestConcentrationOnDamage:
    def test_damage_flags_concentration_check(self):
        char = _make_char(concentration="Bless")
        result = apply_damage(char, 10, "fire")
        assert result["concentration_check_required"] is True
        assert result["concentration_dc"] == 10  # max(10, 10//2)
        assert char.concentration == "Bless"  # not auto-broken

    def test_high_damage_raises_dc(self):
        char = _make_char(hp=50, max_hp=50, concentration="Bless")
        result = apply_damage(char, 30, "fire")
        assert result["concentration_dc"] == 15  # max(10, 30//2)

    def test_knockout_breaks_concentration(self):
        char = _make_char(hp=5, concentration="Shield of Faith")
        result = apply_damage(char, 10, "slashing")
        assert char.concentration is None
        assert result.get("concentration_broken") is True
        assert result.get("unconscious") is True

    def test_no_concentration_no_flag(self):
        char = _make_char()
        result = apply_damage(char, 10, "fire")
        assert "concentration_check_required" not in result

    def test_monster_damage_no_concentration_flag(self):
        """Concentration checks only for player characters."""
        from src.models.monster import Monster
        m = Monster(
            id="m1", name="M", race="M", class_name="monster",
            level=1,
            ability_scores=AbilityScores(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10),
            hp=20, max_hp=20, ac=12, proficiency_bonus=2,
            is_player=False, challenge_rating=1, xp_value=100,
            concentration="Hold Person",
        )
        result = apply_damage(m, 5, "fire")
        # Monsters don't get concentration check flag (is_player=False)
        assert "concentration_check_required" not in result
