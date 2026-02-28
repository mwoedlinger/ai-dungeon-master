"""Tests for the combat engine."""
import pytest
from src.engine.combat import death_save, end_combat, end_turn, start_combat
from src.engine.game_state import GameState
from src.models.combat import CombatState
from src.models.world import WorldState, Location


def make_game_state(fighter, wizard, goblin, goblin_2):
    world = WorldState(
        current_location_id="thornfield",
        locations={"thornfield": Location(id="thornfield", name="Thornfield", description="A village.")},
    )
    return GameState(
        player_character_ids=["aldric", "zara"],
        characters={
            "aldric": fighter,
            "zara": wizard,
            "goblin_1": goblin,
            "goblin_2": goblin_2,
        },
        world=world,
    )


def test_start_combat_sets_active(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    result = start_combat(gs, ["aldric", "zara", "goblin_1", "goblin_2"])
    assert result["success"]
    assert gs.combat.active
    assert len(gs.combat.turn_order) == 4
    assert gs.combat.round == 1


def test_initiative_order_descending(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara", "goblin_1", "goblin_2"])
    inits = [gs.combat.combatants[cid].initiative for cid in gs.combat.turn_order]
    assert inits == sorted(inits, reverse=True)


def test_start_combat_creates_combatants(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara", "goblin_1"])
    for cid in ["aldric", "zara", "goblin_1"]:
        assert cid in gs.combat.combatants
        c = gs.combat.combatants[cid]
        assert c.has_action
        assert c.has_bonus_action
        assert c.has_reaction


def test_end_turn_advances_index(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara", "goblin_1", "goblin_2"])
    first_id = gs.combat.current_combatant_id
    result = end_turn(gs)
    assert result["success"]
    second_id = gs.combat.current_combatant_id
    assert first_id != second_id


def test_end_turn_wraps_around(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara", "goblin_1", "goblin_2"])
    first_id = gs.combat.current_combatant_id
    # Advance through all 4
    for _ in range(4):
        end_turn(gs)
    assert gs.combat.current_combatant_id == first_id
    assert gs.combat.round == 2


def test_end_turn_increments_round(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara", "goblin_1", "goblin_2"])
    assert gs.combat.round == 1
    for _ in range(4):
        end_turn(gs)
    assert gs.combat.round == 2


def test_end_turn_resets_actions(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara", "goblin_1"])
    # Consume action for first combatant
    first_id = gs.combat.current_combatant_id
    gs.combat.consume_action(first_id)
    assert not gs.combat.combatants[first_id].has_action
    # End turn — next combatant should have actions reset
    end_turn(gs)
    next_id = gs.combat.current_combatant_id
    assert gs.combat.combatants[next_id].has_action


def test_end_turn_ticks_conditions(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara"])
    first_id = gs.combat.current_combatant_id
    first_char = gs.get_character(first_id)
    # Apply a 1-round condition
    first_char.conditions.append("poisoned")
    gs.combat.combatants[first_id].condition_durations["poisoned"] = 1
    # End turn — condition should expire
    end_turn(gs)
    assert "poisoned" not in first_char.conditions


def test_end_combat_clears_state(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara", "goblin_1"])
    result = end_combat(gs, xp_awarded=100)
    assert result["success"]
    assert not gs.combat.active
    # Monsters removed
    assert "goblin_1" not in gs.characters


def test_end_combat_awards_xp(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    start_combat(gs, ["aldric", "zara", "goblin_1"])
    initial_xp = fighter.xp
    end_combat(gs, xp_awarded=200)
    # 200 XP split between 2 PCs = 100 each
    assert fighter.xp == initial_xp + 100


def test_end_combat_level_up(fighter, wizard, goblin, goblin_2):
    gs = make_game_state(fighter, wizard, goblin, goblin_2)
    # Set fighter right at level boundary
    fighter.xp = 270  # need 300 for level 2
    fighter.level = 1
    start_combat(gs, ["aldric", "goblin_1"])
    result = end_combat(gs, xp_awarded=100)  # 100 XP → 50 each → 270+50=320 > 300
    assert any(lu["character"] == "Aldric" for lu in result["level_ups"])


def test_death_save_success(fighter):
    fighter.hp = 0
    fighter.conditions = ["unconscious"]
    fighter.death_saves.successes = 0

    # Mock a success roll (10+)
    import src.engine.combat as combat_mod
    import src.engine.dice as dice_mod

    original = dice_mod.roll_dice
    from src.models.combat import DiceResult

    def mock_roll(expr, **kwargs):
        if "d20" in expr:
            return DiceResult(expression=expr, individual_rolls=[15], modifier=0, total=15)
        return original(expr, **kwargs)

    from src.engine.game_state import GameState
    from src.models.world import WorldState, Location
    world = WorldState(
        current_location_id="x",
        locations={"x": Location(id="x", name="X", description="test")},
    )
    gs = GameState(player_character_ids=["aldric"], characters={"aldric": fighter}, world=world)

    # Patch roll_dice inside combat module
    original_combat = combat_mod.roll_dice
    combat_mod.roll_dice = mock_roll
    try:
        result = death_save(gs, "aldric")
        assert result["outcome"] == "success"
        assert fighter.death_saves.successes == 1
    finally:
        combat_mod.roll_dice = original_combat


def test_death_save_critical_failure(fighter):
    fighter.hp = 0
    fighter.conditions = ["unconscious"]
    fighter.death_saves.failures = 0

    import src.engine.combat as combat_mod
    from src.models.combat import DiceResult

    original = combat_mod.roll_dice

    def mock_roll(expr, **kwargs):
        if "d20" in expr:
            return DiceResult(expression=expr, individual_rolls=[1], modifier=0, total=1)
        return original(expr, **kwargs)

    from src.engine.game_state import GameState
    from src.models.world import WorldState, Location
    world = WorldState(
        current_location_id="x",
        locations={"x": Location(id="x", name="X", description="test")},
    )
    gs = GameState(player_character_ids=["aldric"], characters={"aldric": fighter}, world=world)

    combat_mod.roll_dice = mock_roll
    try:
        result = death_save(gs, "aldric")
        assert result["outcome"] == "critical_failure"
        assert fighter.death_saves.failures == 2
    finally:
        combat_mod.roll_dice = original


def test_death_save_nat20_revives(fighter):
    fighter.hp = 0
    fighter.conditions = ["unconscious"]

    import src.engine.combat as combat_mod
    from src.models.combat import DiceResult

    original = combat_mod.roll_dice

    def mock_roll(expr, **kwargs):
        if "d20" in expr:
            return DiceResult(expression=expr, individual_rolls=[20], modifier=0, total=20)
        return original(expr, **kwargs)

    from src.engine.game_state import GameState
    from src.models.world import WorldState, Location
    world = WorldState(
        current_location_id="x",
        locations={"x": Location(id="x", name="X", description="test")},
    )
    gs = GameState(player_character_ids=["aldric"], characters={"aldric": fighter}, world=world)

    combat_mod.roll_dice = mock_roll
    try:
        result = death_save(gs, "aldric")
        assert result["outcome"] == "miraculous_recovery"
        assert fighter.hp == 1
        assert "unconscious" not in fighter.conditions
    finally:
        combat_mod.roll_dice = original


def test_three_failures_kills(fighter):
    fighter.hp = 0
    fighter.conditions = ["unconscious"]
    fighter.death_saves.failures = 2  # one more = dead

    import src.engine.combat as combat_mod
    from src.models.combat import DiceResult

    original = combat_mod.roll_dice

    def mock_roll(expr, **kwargs):
        if "d20" in expr:
            return DiceResult(expression=expr, individual_rolls=[5], modifier=0, total=5)
        return original(expr, **kwargs)

    from src.engine.game_state import GameState
    from src.models.world import WorldState, Location
    world = WorldState(
        current_location_id="x",
        locations={"x": Location(id="x", name="X", description="test")},
    )
    gs = GameState(player_character_ids=["aldric"], characters={"aldric": fighter}, world=world)

    combat_mod.roll_dice = mock_roll
    try:
        result = death_save(gs, "aldric")
        assert result.get("dead")
        assert "dead" in fighter.conditions
    finally:
        combat_mod.roll_dice = original
