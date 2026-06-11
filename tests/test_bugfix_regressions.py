"""Regression tests for the fixes from docs/codebase-review.md."""
from __future__ import annotations

import pytest

from src.engine.combat import death_save, start_combat
from src.engine.dice import roll_dice
from src.engine.rest import long_rest
from src.engine.rules import apply_damage, apply_healing
from src.models.character import AbilityScores, Character


def make_char(**overrides) -> Character:
    defaults = dict(
        id="c1", name="Hero", race="Human", class_name="Fighter", level=3,
        ability_scores=AbilityScores(STR=14, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
        hp=20, max_hp=20, ac=15, proficiency_bonus=2,
        hit_dice_remaining=3, hit_die_type="d10",
    )
    defaults.update(overrides)
    return Character(**defaults)


class TestLongRest:
    def test_dead_character_cannot_long_rest(self):
        char = make_char(hp=0, conditions=["dead"])
        result = long_rest(char)
        assert result["success"] is False
        assert char.hp == 0
        assert "dead" in char.conditions

    def test_exhaustion_drops_one_level(self):
        char = make_char(conditions=["exhaustion_3", "poisoned"])
        long_rest(char)
        assert "exhaustion_2" in char.conditions
        assert "exhaustion_3" not in char.conditions
        assert "poisoned" not in char.conditions

    def test_exhaustion_1_removed_entirely(self):
        char = make_char(conditions=["exhaustion_1"])
        long_rest(char)
        assert char.conditions == []


class TestDamageMitigation:
    def test_player_resistance_halves_damage(self):
        char = make_char(damage_resistances=["fire"])
        result = apply_damage(char, 10, "fire")
        assert result["damage_dealt"] == 5
        assert char.hp == 15

    def test_player_immunity_negates_damage(self):
        char = make_char(damage_immunities=["poison"])
        result = apply_damage(char, 10, "poison")
        assert result["damage_dealt"] == 0
        assert char.hp == 20

    def test_concentration_dc_uses_post_resistance_damage(self):
        char = make_char(damage_resistances=["fire"], concentration="Bless", max_hp=100, hp=100)
        result = apply_damage(char, 50, "fire")  # 25 after resistance
        assert result["concentration_check"]["dc"] == 12  # max(10, 25 // 2)


class TestStableState:
    def test_three_successes_stable_but_unconscious(self):
        char = make_char(hp=0, conditions=["unconscious"])
        char.death_saves.successes = 2
        gs = _FakeGS({char.id: char})
        # Force a success: roll until outcome success or recovery; instead set successes
        # deterministically by monkeypatching is overkill — call until stabilized or dead.
        for _ in range(200):
            char.conditions = ["unconscious"]
            char.death_saves.successes = 2
            char.death_saves.failures = 0
            result = death_save(gs, char.id)
            if result.get("stabilized"):
                break
        assert "stable" in char.conditions
        assert "unconscious" in char.conditions
        assert char.hp == 0

    def test_stable_character_makes_no_death_saves(self):
        char = make_char(hp=0, conditions=["unconscious", "stable"])
        gs = _FakeGS({char.id: char})
        result = death_save(gs, char.id)
        assert result["success"] is False

    def test_damage_breaks_stable(self):
        char = make_char(hp=0, conditions=["unconscious", "stable"])
        result = apply_damage(char, 3, "slashing")
        assert "stable" not in char.conditions
        assert result.get("stable_broken") is True

    def test_healing_revives_stable_character(self):
        char = make_char(hp=0, conditions=["unconscious", "stable"])
        result = apply_healing(char, 5)
        assert result["revived"] is True
        assert "unconscious" not in char.conditions
        assert "stable" not in char.conditions


class _FakeGS:
    def __init__(self, characters):
        self.characters = characters

    def get_character(self, cid):
        return self.characters[cid]


class TestDice:
    def test_keep_highest_with_modifier(self):
        result = roll_dice("4d6kh3+2")
        assert len(result.individual_rolls) == 4
        assert result.modifier == 2
        kept = sorted(result.individual_rolls, reverse=True)[:3]
        assert result.total == sum(kept) + 2

    def test_keep_highest_with_negative_modifier(self):
        result = roll_dice("2d20kh1-1")
        assert result.modifier == -1


class TestUpcastValidation:
    def test_cannot_cast_with_lower_level_slot(self):
        from src.engine.spells import resolve_spell
        from src.models.spells import SpellData, SpellResolution
        spell = SpellData(
            name="Fireball", level=3, resolution=SpellResolution.SAVE_DAMAGE,
            damage_dice="8d6", damage_type="fire", save_ability="DEX",
            casting_time="action", description="A bright streak of flame.",
        )
        caster = make_char(
            spell_slots={1: 2, 3: 1}, max_spell_slots={1: 2, 3: 1},
            spellcasting_ability="INT", known_spells=["Fireball"],
        )
        result = resolve_spell(None, spell, caster, [make_char(id="t")], cast_level=1)
        assert result["success"] is False
        assert caster.spell_slots[1] == 2  # nothing was deducted


class TestInitiativeDeterminism:
    def test_tie_break_is_deterministic_by_name(self):
        chars = {
            f"c{i}": make_char(id=f"c{i}", name=name)
            for i, name in enumerate(["Zed", "Anna", "Mira"])
        }
        gs = _FakeGSCombat(chars)
        import random
        random.seed(42)
        start_combat(gs, list(chars.keys()))
        # With identical DEX, equal initiative rolls must order by name
        order = gs.combat.turn_order
        inits = {cid: gs.combat.combatants[cid].initiative for cid in order}
        for a, b in zip(order, order[1:]):
            if inits[a] == inits[b]:
                assert chars[a].name < chars[b].name


class _FakeGSCombat(_FakeGS):
    combat = None


class TestStorySummary:
    def test_generate_story_summary_uses_full_history(self, monkeypatch):
        """Regression: /summary crashed with AttributeError ('messages')."""
        from src.dm.dungeon_master import DungeonMaster

        dm = DungeonMaster.__new__(DungeonMaster)  # skip backend construction

        class _FakeJournal:
            global_summary = ""
            conversation_summary = ""
            location_summaries = {}
            npc_summaries = {}

            def get_recent_entries(self, limit):
                return []

        class _FakeGameState:
            journal = _FakeJournal()

        class _FakeCM:
            full_history = [
                {"role": "user", "content": "We enter the tavern."},
                {"role": "assistant", "content": "The tavern is dim and smoky."},
            ]

        class _FakeBackend:
            def compress(self, system, messages, max_tokens):
                assert "tavern" in messages[0]["content"]
                return "## The Story So Far\n..."

        dm.game_state = _FakeGameState()
        dm.context_manager = _FakeCM()
        dm.backend = _FakeBackend()

        summary = dm.generate_story_summary()
        assert summary.startswith("## The Story So Far")


class TestStartCombatGuard:
    def _make_game_state(self):
        from src.engine.game_state import GameState
        from src.models.world import WorldState
        chars = {
            "pc1": make_char(id="pc1", name="Aldric"),
            "pc2": make_char(id="pc2", name="Zara"),
        }
        return GameState(
            player_character_ids=["pc1", "pc2"],
            characters=chars,
            world=WorldState(current_location_id="loc", locations={}),
        )

    def test_start_combat_rejected_while_active(self):
        """Regression: a second start_combat re-rolled initiative, reset the
        round counter, and spawned duplicate monsters."""
        from src.dm.tools import ToolDispatcher
        from src.log.event_log import EventLog

        gs = self._make_game_state()
        dispatcher = ToolDispatcher(gs, EventLog())

        first = dispatcher.dispatch("start_combat", {"participant_ids": ["pc1", "pc2"]})
        assert first["success"] is True
        order_before = list(gs.combat.turn_order)
        inits_before = {cid: c.initiative for cid, c in gs.combat.combatants.items()}
        gs.combat.round = 2

        second = dispatcher.dispatch("start_combat", {"participant_ids": ["pc1", "pc2"]})
        assert second["success"] is False
        assert "already active" in second["error"]
        # Existing combat state is untouched
        assert gs.combat.round == 2
        assert gs.combat.turn_order == order_before
        assert {cid: c.initiative for cid, c in gs.combat.combatants.items()} == inits_before
        # No duplicate characters were spawned
        assert set(gs.characters.keys()) == {"pc1", "pc2"}
