"""Tests for the dice engine."""
import pytest
from src.engine.dice import roll_dice


def test_basic_roll():
    result = roll_dice("1d6")
    assert result.expression == "1d6"
    assert len(result.individual_rolls) == 1
    assert 1 <= result.total <= 6
    assert result.modifier == 0


def test_multiple_dice():
    result = roll_dice("2d6")
    assert len(result.individual_rolls) == 2
    assert 2 <= result.total <= 12


def test_positive_modifier():
    result = roll_dice("1d6+3")
    assert result.modifier == 3
    assert result.total == result.individual_rolls[0] + 3


def test_negative_modifier():
    result = roll_dice("1d6-2")
    assert result.modifier == -2
    assert result.total == result.individual_rolls[0] - 2


def test_d20_no_adv():
    result = roll_dice("1d20")
    assert 1 <= result.total <= 20
    assert result.kept_roll is None


def test_advantage():
    # Run many times and check that we get max of two rolls
    for _ in range(20):
        result = roll_dice("1d20", advantage=True)
        assert result.advantage is True
        assert len(result.individual_rolls) == 2
        assert result.kept_roll == max(result.individual_rolls)
        assert result.total == result.kept_roll


def test_disadvantage():
    for _ in range(20):
        result = roll_dice("1d20", disadvantage=True)
        assert result.disadvantage is True
        assert len(result.individual_rolls) == 2
        assert result.kept_roll == min(result.individual_rolls)
        assert result.total == result.kept_roll


def test_advantage_and_disadvantage_cancel():
    # Advantage + disadvantage = normal roll
    result = roll_dice("1d20", advantage=True, disadvantage=True)
    assert result.advantage is False
    assert result.disadvantage is False
    assert result.kept_roll is None
    assert len(result.individual_rolls) == 1


def test_keep_highest():
    result = roll_dice("4d6kh3")
    assert len(result.individual_rolls) == 4
    # Total should be sum of top 3
    expected = sum(sorted(result.individual_rolls, reverse=True)[:3])
    assert result.total == expected


def test_zero_dice():
    result = roll_dice("0d6")
    assert result.total == 0
    assert result.individual_rolls == []


def test_zero_dice_with_modifier():
    result = roll_dice("0d6+5")
    assert result.total == 5


def test_one_die_one_side():
    result = roll_dice("1d1")
    assert result.total == 1 + result.modifier


def test_d_shorthand():
    # "d6" means "1d6"
    result = roll_dice("d6")
    assert 1 <= result.total <= 6


def test_implicit_one_die_keep_highest():
    result = roll_dice("1d20")
    assert len(result.individual_rolls) == 1


def test_invalid_expression():
    with pytest.raises(ValueError):
        roll_dice("not_a_dice")


def test_large_dice():
    result = roll_dice("10d12")
    assert len(result.individual_rolls) == 10
    assert 10 <= result.total <= 120


def test_crit_detection_via_kept_roll():
    # Advantage roll: kept_roll is the max
    for _ in range(100):
        r = roll_dice("1d20", advantage=True)
        assert r.kept_roll is not None
        if r.kept_roll == 20:
            assert r.individual_rolls[0] == 20 or r.individual_rolls[1] == 20
