"""Tests for the spell engine."""
import pytest
from src.engine.spells import _apply_upcast, resolve_spell
from src.models.spells import SpellData, SpellResolution


# --- Test spell fixtures ---

@pytest.fixture
def fireball() -> SpellData:
    return SpellData(
        name="Fireball",
        level=3,
        resolution=SpellResolution.SAVE_DAMAGE,
        casting_time="action",
        damage_dice="8d6",
        damage_type="fire",
        save_ability="DEX",
        upcast_bonus="+1d6 per level",
        description="A bright streak flashes from your pointing finger...",
        aoe=True,
    )


@pytest.fixture
def fire_bolt() -> SpellData:
    return SpellData(
        name="Fire Bolt",
        level=0,
        resolution=SpellResolution.ATTACK_ROLL,
        casting_time="action",
        damage_dice="2d10",
        damage_type="fire",
        description="You hurl a mote of fire at a creature.",
    )


@pytest.fixture
def cure_wounds() -> SpellData:
    return SpellData(
        name="Cure Wounds",
        level=1,
        resolution=SpellResolution.HEALING,
        casting_time="action",
        healing_dice="1d8",
        upcast_bonus="+1d8 per level",
        description="A creature you touch regains hit points.",
    )


@pytest.fixture
def hold_person() -> SpellData:
    return SpellData(
        name="Hold Person",
        level=2,
        resolution=SpellResolution.SAVE_EFFECT,
        casting_time="action",
        concentration=True,
        save_ability="WIS",
        duration_rounds=10,
        condition_effect="paralyzed",
        description="You attempt to hold a humanoid creature.",
    )


@pytest.fixture
def mage_armor() -> SpellData:
    return SpellData(
        name="Mage Armor",
        level=1,
        resolution=SpellResolution.BUFF,
        casting_time="action",
        buff_effect="AC becomes 13 + DEX modifier",
        duration_rounds=None,
        description="A protective magical force surrounds the target.",
    )


@pytest.fixture
def prestidigitation() -> SpellData:
    return SpellData(
        name="Prestidigitation",
        level=0,
        resolution=SpellResolution.NARRATIVE,
        casting_time="action",
        description="This spell is a minor magical trick.",
    )


def make_game_state_for_spells(wizard, goblin):
    """Create minimal GameState for spell tests."""
    from src.engine.game_state import GameState
    from src.models.world import WorldState, Location
    world = WorldState(
        current_location_id="x",
        locations={"x": Location(id="x", name="X", description="test")},
    )
    return GameState(
        player_character_ids=["zara"],
        characters={"zara": wizard, "goblin_1": goblin},
        world=world,
    )


# --- Slot deduction tests ---

def test_slot_deducted_on_cast(wizard, goblin, fireball):
    gs = make_game_state_for_spells(wizard, goblin)
    wizard.spell_slots = {3: 2}
    wizard.max_spell_slots = {3: 2}
    result = resolve_spell(gs, fireball, wizard, [goblin], cast_level=3)
    assert result["success"]
    assert wizard.spell_slots[3] == 1


def test_no_slot_returns_error(wizard, goblin, fireball):
    gs = make_game_state_for_spells(wizard, goblin)
    wizard.spell_slots = {3: 0}
    result = resolve_spell(gs, fireball, wizard, [goblin], cast_level=3)
    assert not result["success"]
    assert "spell slots" in result["error"].lower()


def test_cantrip_no_slot_needed(wizard, goblin, fire_bolt):
    gs = make_game_state_for_spells(wizard, goblin)
    wizard.spell_slots = {}
    result = resolve_spell(gs, fire_bolt, wizard, [goblin], cast_level=0)
    assert result["success"]  # cantrips don't consume slots


# --- Upcast tests ---

def test_upcast_damage_bonus(wizard, goblin, fireball):
    """Fireball at level 4 should use 9d6 instead of 8d6."""
    expr = _apply_upcast("8d6", fireball, cast_level=4)
    assert expr == "9d6"


def test_upcast_multiple_levels(wizard, goblin, fireball):
    expr = _apply_upcast("8d6", fireball, cast_level=6)
    assert expr == "11d6"


def test_upcast_at_base_level_no_change(wizard, goblin, fireball):
    expr = _apply_upcast("8d6", fireball, cast_level=3)
    assert expr == "8d6"


def test_upcast_healing(wizard, cure_wounds):
    expr = _apply_upcast("1d8", cure_wounds, cast_level=3)
    assert expr == "3d8"


# --- Concentration tests ---

def test_concentration_set_on_cast(wizard, goblin, hold_person):
    gs = make_game_state_for_spells(wizard, goblin)
    wizard.spell_slots = {2: 1}
    resolve_spell(gs, hold_person, wizard, [goblin], cast_level=2)
    assert wizard.concentration == "Hold Person"


def test_concentration_drops_old(wizard, goblin, hold_person, mage_armor):
    gs = make_game_state_for_spells(wizard, goblin)
    mage_armor_conc = SpellData(
        name="Bless",
        level=1,
        resolution=SpellResolution.BUFF,
        casting_time="action",
        concentration=True,
        buff_effect="+1d4 to attack rolls",
        description="Bless up to three creatures.",
    )
    wizard.concentration = "Bless"
    wizard.spell_slots = {2: 1}
    result = resolve_spell(gs, hold_person, wizard, [goblin], cast_level=2)
    assert result.get("dropped_concentration") == "Bless"
    assert wizard.concentration == "Hold Person"


# --- Resolution tier tests ---

def test_save_damage_returns_targets(wizard, goblin, fireball):
    gs = make_game_state_for_spells(wizard, goblin)
    wizard.spell_slots = {3: 2}
    result = resolve_spell(gs, fireball, wizard, [goblin], cast_level=3)
    assert result["success"]
    assert "targets" in result
    assert len(result["targets"]) == 1
    assert "damage" in result["targets"][0]


def test_attack_roll_spell_returns_hits(wizard, goblin, fire_bolt):
    gs = make_game_state_for_spells(wizard, goblin)
    results = []
    for _ in range(20):
        # Reset goblin HP
        goblin.hp = goblin.max_hp
        r = resolve_spell(gs, fire_bolt, wizard, [goblin], cast_level=0)
        results.append(r)
    assert all(r["success"] for r in results)
    assert any(r["targets"][0]["hits"] for r in results)


def test_healing_spell_heals_target(wizard, goblin, cure_wounds):
    gs = make_game_state_for_spells(wizard, goblin)
    wizard.spell_slots = {1: 1}
    wizard.hp = 10
    wizard.max_hp = 19
    result = resolve_spell(gs, cure_wounds, wizard, [wizard], cast_level=1)
    assert result["success"]
    assert result.get("healed", 0) > 0


def test_buff_spell_returns_effect(wizard, goblin, mage_armor):
    gs = make_game_state_for_spells(wizard, goblin)
    wizard.spell_slots = {1: 1}
    result = resolve_spell(gs, mage_armor, wizard, [wizard], cast_level=1)
    assert result["success"]
    assert result.get("effect") is not None


def test_save_effect_applies_condition(wizard, goblin, hold_person):
    """On failed save, condition should be applied."""
    import src.engine.spells as spells_mod
    from src.models.combat import DiceResult

    original = spells_mod.saving_throw

    def mock_save(char, ability, dc, **kwargs):
        from src.models.combat import CheckResult, DiceResult
        r = DiceResult(expression="1d20", individual_rolls=[1], modifier=0, total=1)
        return CheckResult(roll=r, modifier=0, total=1, dc=dc, success=False)

    spells_mod.saving_throw = mock_save
    try:
        gs = make_game_state_for_spells(wizard, goblin)
        wizard.spell_slots = {2: 1}
        result = resolve_spell(gs, hold_person, wizard, [goblin], cast_level=2)
        assert result["success"]
        assert result["targets"][0]["effect_applied"]
        assert "paralyzed" in goblin.conditions
    finally:
        spells_mod.saving_throw = original


def test_narrative_spell_returns_narrative_only(wizard, goblin, prestidigitation):
    gs = make_game_state_for_spells(wizard, goblin)
    result = resolve_spell(gs, prestidigitation, wizard, [], cast_level=0)
    assert result["success"]
    assert result.get("narrative_only")
