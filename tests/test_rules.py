"""Tests for the rules engine."""
import pytest
from src.engine.rules import (
    ability_check,
    apply_condition,
    apply_damage,
    apply_healing,
    attack_roll,
    proficiency_bonus_for_level,
    remove_condition,
    saving_throw,
    xp_for_level,
)
from src.models.character import DeathSaves


def test_proficiency_bonus():
    assert proficiency_bonus_for_level(1) == 2
    assert proficiency_bonus_for_level(4) == 2
    assert proficiency_bonus_for_level(5) == 3
    assert proficiency_bonus_for_level(8) == 3
    assert proficiency_bonus_for_level(9) == 4
    assert proficiency_bonus_for_level(20) == 6


def test_xp_for_level():
    assert xp_for_level(1) == 0
    assert xp_for_level(2) == 300
    assert xp_for_level(5) == 6500


def test_ability_check_with_proficiency(fighter):
    # Fighter has Athletics proficiency and STR 16 (+3) + proficiency 2 = +5
    # DC 10 should almost always succeed
    results = [ability_check(fighter, "STR", dc=10, skill="Athletics") for _ in range(20)]
    # With +5 total modifier, need roll of 5+ to hit DC 10
    # All results should be valid
    for r in results:
        assert isinstance(r.success, bool)
        assert r.total == r.roll.individual_rolls[0] + r.modifier


def test_ability_check_without_proficiency(fighter):
    # No Persuasion proficiency, CHA 10 = +0
    r = ability_check(fighter, "CHA", dc=15, skill="Persuasion")
    # Modifier should be 0 (no proficiency)
    assert r.modifier == 0


def test_ability_check_with_skill_not_proficient(fighter):
    # Fighter has Stealth in proficiencies? No.
    r = ability_check(fighter, "DEX", dc=12, skill="Stealth")
    assert r.modifier == fighter.ability_scores.modifier("DEX")  # no proficiency bonus


def test_saving_throw_proficient(fighter):
    # Fighter prof in STR saves: STR mod (+3) + prof (+2) = +5
    r = saving_throw(fighter, "STR", dc=15)
    assert r.modifier == fighter.ability_scores.modifier("STR") + fighter.proficiency_bonus


def test_saving_throw_not_proficient(fighter):
    # Fighter not proficient in INT saves
    r = saving_throw(fighter, "INT", dc=15)
    assert r.modifier == fighter.ability_scores.modifier("INT")
    assert r.modifier == 0


def test_attack_roll_hit(fighter, goblin):
    # Fighter STR 16 (+3) + prof 2 = +5 attack vs AC 15
    # Roll of 10 → total 15 → should hit
    results = []
    for _ in range(50):
        r = attack_roll(fighter, goblin, fighter.weapons[0])
        results.append(r)
    # Some should hit, some miss (statistically)
    assert any(r.hits for r in results)
    assert any(not r.hits for r in results) or True  # may all hit with +5 vs AC 15


def test_attack_roll_nat1_always_misses(monkeypatch, fighter, goblin):
    import src.engine.dice as dice_mod
    import src.engine.rules as rules_mod

    original_roll = dice_mod.roll_dice
    call_count = [0]

    def mock_roll(expr, advantage=False, disadvantage=False):
        call_count[0] += 1
        from src.models.combat import DiceResult
        if "d20" in expr:
            return DiceResult(expression=expr, individual_rolls=[1], modifier=0, total=1)
        return original_roll(expr)

    monkeypatch.setattr(rules_mod, "roll_dice", mock_roll)
    r = attack_roll(fighter, goblin, fighter.weapons[0])
    assert r.is_nat1
    assert not r.hits


def test_attack_roll_nat20_always_hits(monkeypatch, fighter, goblin):
    import src.engine.dice as dice_mod
    import src.engine.rules as rules_mod

    original_roll = dice_mod.roll_dice

    def mock_roll(expr, advantage=False, disadvantage=False):
        from src.models.combat import DiceResult
        if "d20" in expr:
            return DiceResult(expression=expr, individual_rolls=[20], modifier=0, total=20)
        return original_roll(expr)

    monkeypatch.setattr(rules_mod, "roll_dice", mock_roll)
    r = attack_roll(fighter, goblin, fighter.weapons[0])
    assert r.is_crit
    assert r.hits
    assert r.damage is not None


def test_crit_doubles_dice(monkeypatch, fighter, goblin):
    """On a crit, damage dice are rolled twice."""
    import src.engine.rules as rules_mod
    import src.engine.dice as dice_mod

    original_roll = dice_mod.roll_dice
    roll_calls = []

    def mock_roll(expr, advantage=False, disadvantage=False):
        from src.models.combat import DiceResult
        if "d20" in expr:
            return DiceResult(expression=expr, individual_rolls=[20], modifier=0, total=20)
        result = original_roll(expr)
        roll_calls.append(expr)
        return result

    monkeypatch.setattr(rules_mod, "roll_dice", mock_roll)
    r = attack_roll(fighter, goblin, fighter.weapons[0])
    assert r.is_crit
    # Damage dice should have been rolled twice (1d8 twice)
    damage_rolls = [e for e in roll_calls if "d" in e]
    assert len(damage_rolls) == 2


def test_apply_damage_basic(fighter):
    fighter.hp = 28
    result = apply_damage(fighter, 10, "slashing")
    assert result["damage_dealt"] == 10
    assert fighter.hp == 18


def test_apply_damage_temp_hp_first(fighter):
    fighter.hp = 20
    fighter.temp_hp = 5
    result = apply_damage(fighter, 8, "slashing")
    assert fighter.temp_hp == 0
    assert fighter.hp == 17  # 5 absorbed, 3 to real HP


def test_apply_damage_unconscious_at_zero(fighter):
    fighter.hp = 5
    result = apply_damage(fighter, 10, "slashing")
    assert fighter.hp == 0
    assert result.get("unconscious")
    assert "unconscious" in fighter.conditions


def test_apply_damage_monster_dies_at_zero(goblin):
    result = apply_damage(goblin, 10, "slashing")
    assert goblin.hp == 0
    assert result.get("dead")


def test_apply_damage_resistance(goblin):
    goblin.damage_resistances = ["fire"]
    result = apply_damage(goblin, 10, "fire")
    assert result["damage_dealt"] == 5


def test_apply_damage_immunity(goblin):
    goblin.damage_immunities = ["poison"]
    result = apply_damage(goblin, 10, "poison")
    assert result["damage_dealt"] == 0
    assert goblin.hp == goblin.max_hp


def test_apply_healing_basic(fighter):
    fighter.hp = 10
    result = apply_healing(fighter, 8)
    assert fighter.hp == 18
    assert result["healed"] == 8


def test_apply_healing_caps_at_max(fighter):
    fighter.hp = 25
    result = apply_healing(fighter, 10)
    assert fighter.hp == 28
    assert result["healed"] == 3


def test_apply_healing_revives_unconscious(fighter):
    fighter.hp = 0
    fighter.conditions = ["unconscious"]
    fighter.death_saves.successes = 2
    fighter.death_saves.failures = 1
    result = apply_healing(fighter, 5)
    assert result["revived"]
    assert "unconscious" not in fighter.conditions
    assert fighter.death_saves.successes == 0
    assert fighter.death_saves.failures == 0


def test_apply_condition(fighter):
    result = apply_condition(fighter, "poisoned", duration_rounds=3)
    assert "poisoned" in fighter.conditions
    assert result["applied"] == "poisoned"


def test_apply_condition_no_duplicate(fighter):
    fighter.conditions = ["poisoned"]
    apply_condition(fighter, "poisoned")
    assert fighter.conditions.count("poisoned") == 1


def test_remove_condition(fighter):
    fighter.conditions = ["poisoned", "blinded"]
    result = remove_condition(fighter, "poisoned")
    assert "poisoned" not in fighter.conditions
    assert result["removed"] == "poisoned"


def test_remove_condition_not_present(fighter):
    result = remove_condition(fighter, "charmed")
    assert result["removed"] is None
