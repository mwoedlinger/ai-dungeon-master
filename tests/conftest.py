"""Shared fixtures for all tests."""
import pytest

from src.models.character import AbilityScores, Armor, Character, Weapon
from src.models.monster import Monster, MonsterAction


@pytest.fixture
def fighter() -> Character:
    return Character(
        id="aldric",
        name="Aldric",
        race="Human",
        class_name="Fighter",
        level=3,
        xp=900,
        ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
        hp=28,
        max_hp=28,
        ac=16,
        proficiency_bonus=2,
        skill_proficiencies=["Athletics", "Perception"],
        weapon_proficiencies=["martial", "simple"],
        armor_proficiencies=["light", "medium", "heavy", "shields"],
        saving_throw_proficiencies=["STR", "CON"],
        hit_dice_remaining=3,
        hit_die_type="d10",
        weapons=[
            Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing"),
            Weapon(name="Handaxe", damage_dice="1d6", damage_type="slashing", properties=["ranged"]),
        ],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
    )


@pytest.fixture
def wizard() -> Character:
    return Character(
        id="zara",
        name="Zara",
        race="Half-Elf",
        class_name="Wizard",
        level=3,
        xp=900,
        ability_scores=AbilityScores(STR=8, DEX=14, CON=12, INT=16, WIS=12, CHA=14),
        hp=19,
        max_hp=19,
        ac=13,
        proficiency_bonus=2,
        skill_proficiencies=["Arcana", "History", "Investigation"],
        weapon_proficiencies=["simple"],
        armor_proficiencies=["light"],
        saving_throw_proficiencies=["INT", "WIS"],
        spell_slots={1: 4, 2: 2},
        max_spell_slots={1: 4, 2: 2},
        spellcasting_ability="INT",
        known_spells=["Fire Bolt", "Magic Missile", "Fireball"],
        hit_dice_remaining=3,
        hit_die_type="d6",
        weapons=[
            Weapon(name="Quarterstaff", damage_dice="1d6", damage_type="bludgeoning"),
        ],
    )


@pytest.fixture
def goblin() -> Monster:
    return Monster(
        id="goblin_1",
        name="Goblin",
        race="Goblin",
        class_name="monster",
        level=1,
        ability_scores=AbilityScores(STR=8, DEX=14, CON=10, INT=10, WIS=8, CHA=8),
        hp=7,
        max_hp=7,
        ac=15,
        proficiency_bonus=2,
        is_player=False,
        challenge_rating=0.25,
        xp_value=50,
        actions=[
            MonsterAction(
                name="Scimitar",
                description="Melee attack with scimitar",
                action_type="action",
                attack_bonus=4,
                damage_dice="1d6",
                damage_type="slashing",
            )
        ],
        weapons=[
            Weapon(name="Scimitar", damage_dice="1d6", damage_type="slashing"),
        ],
    )


@pytest.fixture
def goblin_2() -> Monster:
    return Monster(
        id="goblin_2",
        name="Goblin 2",
        race="Goblin",
        class_name="monster",
        level=1,
        ability_scores=AbilityScores(STR=8, DEX=14, CON=10, INT=10, WIS=8, CHA=8),
        hp=7,
        max_hp=7,
        ac=15,
        proficiency_bonus=2,
        is_player=False,
        challenge_rating=0.25,
        xp_value=50,
        actions=[
            MonsterAction(
                name="Scimitar",
                description="Melee attack with scimitar",
                action_type="action",
                attack_bonus=4,
                damage_dice="1d6",
                damage_type="slashing",
            )
        ],
        weapons=[
            Weapon(name="Scimitar", damage_dice="1d6", damage_type="slashing"),
        ],
    )
