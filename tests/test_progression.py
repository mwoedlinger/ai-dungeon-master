"""Tests for class features, spell progression, and level-up logic."""
from __future__ import annotations

import pytest

from src.engine.progression import (
    CLASS_FEATURES,
    PREPARED_CASTERS,
    SPELLS_LEARNED_PER_LEVEL,
    apply_level_up,
    learn_spell,
)
from src.models.character import AbilityScores, Character


def _make_char(class_name: str, level: int, **kwargs) -> Character:
    """Helper to create a character at a given level."""
    defaults = dict(
        id=class_name.lower(),
        name=class_name,
        race="Human",
        class_name=class_name,
        level=level,
        xp=0,
        ability_scores=AbilityScores(STR=16, DEX=14, CON=14, INT=10, WIS=12, CHA=10),
        hp=20,
        max_hp=20,
        ac=16,
        proficiency_bonus=2,
        saving_throw_proficiencies=["STR", "CON"],
        hit_dice_remaining=level,
        hit_die_type="d10",
    )
    defaults.update(kwargs)
    return Character(**defaults)


# ── Task 1: Class Features ──


class TestFighterFeatures:
    def test_level2_gains_action_surge(self):
        char = _make_char("Fighter", level=2)
        result = apply_level_up(char)
        assert "action_surge" in char.class_resources
        assert char.class_resources["action_surge"] == 1
        assert "Action Surge" in result["features_gained"]

    def test_level5_gains_extra_attack(self):
        char = _make_char("Fighter", level=5)
        result = apply_level_up(char)
        assert char.class_resources.get("extra_attack") == 1
        assert "Extra Attack" in result["features_gained"]

    def test_level9_gains_indomitable(self):
        char = _make_char("Fighter", level=9)
        result = apply_level_up(char)
        assert char.class_resources.get("indomitable") == 1
        assert "Indomitable" in result["features_gained"]


class TestRogueFeatures:
    def test_sneak_attack_scales(self):
        """Sneak Attack dice should be (level+1)//2."""
        char = _make_char("Rogue", level=1, hit_die_type="d8")
        result = apply_level_up(char)
        assert char.class_resources["sneak_attack_dice"] == 1

        # Level up to 3 — sneak attack should be 2
        char.level = 3
        result = apply_level_up(char)
        assert char.class_resources["sneak_attack_dice"] == 2

    def test_level2_gains_cunning_action(self):
        char = _make_char("Rogue", level=2, hit_die_type="d8")
        result = apply_level_up(char)
        assert "Cunning Action" in result["features_gained"]

    def test_level7_gains_evasion(self):
        char = _make_char("Rogue", level=7, hit_die_type="d8")
        result = apply_level_up(char)
        assert char.class_resources.get("evasion") == 1
        assert "Evasion" in result["features_gained"]


class TestMonkFeatures:
    def test_ki_scales_with_level(self):
        char = _make_char("Monk", level=2, hit_die_type="d8")
        apply_level_up(char)
        assert char.class_resources["ki"] == 2

        char.level = 5
        apply_level_up(char)
        assert char.class_resources["ki"] == 5

    def test_level5_extra_attack(self):
        char = _make_char("Monk", level=5, hit_die_type="d8")
        result = apply_level_up(char)
        assert char.class_resources.get("extra_attack") == 1


class TestBardFeatures:
    def test_bardic_inspiration_scales_with_cha(self):
        char = _make_char("Bard", level=1, hit_die_type="d8",
                          ability_scores=AbilityScores(STR=8, DEX=14, CON=12, INT=10, WIS=12, CHA=16))
        apply_level_up(char)
        assert char.class_resources["bardic_inspiration"] == 3  # CHA mod


class TestASIAndFeaturesCombo:
    def test_level4_fighter_asi_and_no_feature(self):
        char = _make_char("Fighter", level=4)
        result = apply_level_up(char)
        assert result["asi_available"] is True
        # Fighter level 4 has no class features
        assert result["features_gained"] == []


class TestResultDict:
    def test_result_contains_features_and_spell_progression(self):
        char = _make_char("Fighter", level=2)
        result = apply_level_up(char)
        assert "features_gained" in result
        assert "spell_progression" in result
        assert isinstance(result["features_gained"], list)
        assert isinstance(result["spell_progression"], dict)


# ── Task 2: Spell Progression ──


class TestSpellProgression:
    def test_wizard_gets_spells_to_learn(self):
        char = _make_char(
            "Wizard", level=4, hit_die_type="d6",
            spellcasting_ability="INT",
            spell_slots={1: 4, 2: 3},
            max_spell_slots={1: 4, 2: 3},
        )
        result = apply_level_up(char)
        assert result["spell_progression"]["spells_to_learn"] == 2

    def test_cleric_is_prepared_caster(self):
        char = _make_char(
            "Cleric", level=3, hit_die_type="d8",
            spellcasting_ability="WIS",
            spell_slots={1: 4, 2: 2},
            max_spell_slots={1: 4, 2: 2},
        )
        result = apply_level_up(char)
        assert result["spell_progression"].get("prepared_caster") is True
        assert "spells_to_learn" not in result["spell_progression"]

    def test_fighter_no_spell_progression(self):
        char = _make_char("Fighter", level=2)
        result = apply_level_up(char)
        assert result["spell_progression"] == {}

    def test_sorcerer_learns_one_spell(self):
        char = _make_char(
            "Sorcerer", level=3, hit_die_type="d6",
            spellcasting_ability="CHA",
            spell_slots={1: 4, 2: 2},
            max_spell_slots={1: 4, 2: 2},
        )
        result = apply_level_up(char)
        assert result["spell_progression"]["spells_to_learn"] == 1


class TestLearnSpell:
    @pytest.fixture(autouse=True)
    def _load_srd(self):
        from src.campaign.loader import load_srd_data
        load_srd_data()

    def test_learn_valid_spell(self):
        char = _make_char(
            "Wizard", level=3, hit_die_type="d6",
            spellcasting_ability="INT",
            max_spell_slots={1: 4, 2: 2},
            known_spells=["Magic Missile"],
        )
        result = learn_spell(char, "Shield", max_spell_level=2)
        assert result["success"] is True
        assert "Shield" in char.known_spells

    def test_learn_duplicate_spell(self):
        char = _make_char(
            "Wizard", level=3, hit_die_type="d6",
            known_spells=["Magic Missile"],
        )
        result = learn_spell(char, "Magic Missile", max_spell_level=2)
        assert result["success"] is False
        assert "already knows" in result["error"]

    def test_learn_unknown_spell(self):
        char = _make_char("Wizard", level=3, hit_die_type="d6")
        result = learn_spell(char, "Totally Fake Spell", max_spell_level=2)
        assert result["success"] is False
        assert "not found" in result["error"]
