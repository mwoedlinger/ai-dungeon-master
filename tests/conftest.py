"""Shared fixtures for all tests."""
import os
import random
from unittest.mock import MagicMock

import pytest

from src.engine.game_state import GameState
from src.log.event_log import EventLog
from src.models.character import AbilityScores, Armor, Character, Weapon
from src.models.monster import Monster, MonsterAction
from src.models.world import Location, WorldState


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


# --- Deterministic randomness -------------------------------------------------

@pytest.fixture(autouse=True)
def _deterministic_rng():
    """Give every test a fresh, seeded engine generator.

    Kills cross-test RNG bleed: a test that consumes rolls can no longer shift
    the sequence a later test sees.
    """
    from src.engine import dice
    # Overridable so the suite can be swept across seeds; a test that only
    # passes at one seed is a test asserting on noise.
    seed = int(os.environ.get("DW_TEST_SEED", 0xD1CE))
    dice.set_rng(random.Random(seed))
    yield


# --- Shared world / state fixtures -------------------------------------------

@pytest.fixture
def world() -> WorldState:
    return WorldState(
        current_location_id="tavern",
        locations={
            "tavern": Location(
                id="tavern",
                name="The Rusty Flagon",
                description="A cramped taproom that smells of spilled ale and woodsmoke.",
                connected_to=["road"],
            ),
            "road": Location(
                id="road",
                name="The King's Road",
                description="A rutted dirt road running north out of town.",
                connected_to=["tavern"],
            ),
        },
    )


@pytest.fixture
def game_state(fighter, wizard, world) -> GameState:
    """Two-PC party in a tavern. The default state for new tests."""
    return GameState(
        player_character_ids=[fighter.id, wizard.id],
        characters={fighter.id: fighter, wizard.id: wizard},
        world=world,
    )


@pytest.fixture
def game_state_with_goblins(game_state, goblin, goblin_2) -> GameState:
    """The same party with two goblins added.

    Deliberately extends `game_state` rather than building a second object, so
    that `dispatcher` and `event_log` — which bind to `game_state` — operate on
    exactly this state. Two GameStates in one test is a silent no-op factory.
    """
    game_state.characters[goblin.id] = goblin
    game_state.characters[goblin_2.id] = goblin_2
    return game_state


@pytest.fixture
def event_log(game_state) -> EventLog:
    return EventLog(game_state)


@pytest.fixture
def dispatcher(game_state, event_log, tmp_path):
    from src.dm.tools import ToolDispatcher
    return ToolDispatcher(
        game_state, event_log, save_path=str(tmp_path / "save.json"),
    )


@pytest.fixture
def campaign_stub():
    """Stands in for CampaignData without touching disk."""
    stub = MagicMock()
    stub.get_location_context.return_value = "## Location\nThe Rusty Flagon — a cramped taproom."
    stub.encounter_tables = {}
    return stub


@pytest.fixture
def dungeon_master(game_state, campaign_stub, event_log, tmp_path):
    """A DungeonMaster wired to a no-op backend.

    Tests that drive `process_player_input` should pass their own
    `ScriptedBackend` instead of using this fixture.
    """
    from src.dm.dungeon_master import DungeonMaster
    from tests.support.scripted_backend import ScriptedBackend

    return DungeonMaster(
        game_state, campaign_stub, event_log,
        save_path=str(tmp_path / "save.json"),
        backend=ScriptedBackend.narration("Nothing happens."),
    )
