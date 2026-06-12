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
            char.hp = 0  # a nat-20 recovery mid-loop sets hp=1; reset each try
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


class TestConversationPersistence:
    def test_history_survives_save_load(self, tmp_path):
        from src.engine.game_state import GameState
        from src.models.world import WorldState

        gs = GameState(
            player_character_ids=["pc1"],
            characters={"pc1": make_char(id="pc1")},
            world=WorldState(current_location_id="loc", locations={}),
        )
        gs.conversation_history.extend([
            {"role": "user", "content": "We enter the tavern."},
            {"role": "assistant", "content": "The tavern is dim and smoky."},
        ])
        path = tmp_path / "save.json"
        gs.save(path)
        loaded = GameState.load(path)
        assert loaded.conversation_history == gs.conversation_history

    def test_context_manager_aliases_game_state_history(self):
        from unittest.mock import MagicMock
        from src.dm.context import ContextManager
        from src.engine.game_state import GameState
        from src.models.world import WorldState

        gs = GameState(
            player_character_ids=["pc1"],
            characters={"pc1": make_char(id="pc1")},
            world=WorldState(current_location_id="loc", locations={}),
        )
        cm = ContextManager(MagicMock(), gs)
        cm.add_message({"role": "user", "content": "hello"})
        assert gs.conversation_history == [{"role": "user", "content": "hello"}]
        # Rebinding (as compression does) must also flow through to GameState
        cm.full_history = []
        assert gs.conversation_history == []

    def test_old_save_without_history_loads(self, tmp_path):
        import json
        from src.engine.game_state import GameState
        from src.models.world import WorldState

        gs = GameState(
            player_character_ids=["pc1"],
            characters={"pc1": make_char(id="pc1")},
            world=WorldState(current_location_id="loc", locations={}),
        )
        path = tmp_path / "save.json"
        gs.save(path)
        data = json.loads(path.read_text())
        del data["conversation_history"]
        data["version"] = 1
        path.write_text(json.dumps(data))
        loaded = GameState.load(path)
        assert loaded.conversation_history == []


class TestToolSchemaSizing:
    def test_small_context_gets_core_set(self):
        from src.dm.tools import ALL_TOOL_SCHEMAS, CORE_TOOL_SCHEMAS, get_tool_schemas
        assert get_tool_schemas(8_000) is CORE_TOOL_SCHEMAS
        assert get_tool_schemas(200_000) is ALL_TOOL_SCHEMAS
        assert len(CORE_TOOL_SCHEMAS) < len(ALL_TOOL_SCHEMAS)
        core_names = {s["name"] for s in CORE_TOOL_SCHEMAS}
        assert {"attack", "cast_spell", "end_turn", "save_game"} <= core_names


class TestOpportunityAttack:
    def _combat_setup(self):
        from src.dm.tools import ToolDispatcher
        from src.engine.game_state import GameState
        from src.log.event_log import EventLog
        from src.models.character import Weapon
        from src.models.world import WorldState

        sword = Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")
        bow = Weapon(name="Shortbow", damage_dice="1d6", damage_type="piercing",
                     properties=["ranged"])
        chars = {
            "pc1": make_char(id="pc1", name="Aldric", weapons=[sword.model_copy(), bow]),
            "pc2": make_char(id="pc2", name="Zara", weapons=[sword.model_copy()]),
        }
        gs = GameState(
            player_character_ids=["pc1", "pc2"],
            characters=chars,
            world=WorldState(current_location_id="loc", locations={}),
        )
        dispatcher = ToolDispatcher(gs, EventLog())
        dispatcher.dispatch("start_combat", {"participant_ids": ["pc1", "pc2"]})
        return gs, dispatcher

    def _off_turn_attacker(self, gs):
        """Return (attacker_id, target_id) where the attacker is NOT current."""
        current = gs.combat.current_combatant_id
        other = next(cid for cid in gs.combat.turn_order if cid != current)
        return other, current

    def test_opportunity_attack_consumes_reaction(self):
        gs, dispatcher = self._combat_setup()
        attacker, target = self._off_turn_attacker(gs)
        result = dispatcher.dispatch("opportunity_attack", {
            "attacker_id": attacker, "target_id": target, "weapon_name": "Longsword",
        })
        assert result["success"] is True
        assert gs.combat.combatants[attacker].has_reaction is False
        # Second one in the same round is rejected
        again = dispatcher.dispatch("opportunity_attack", {
            "attacker_id": attacker, "target_id": target, "weapon_name": "Longsword",
        })
        assert again["success"] is False

    def test_opportunity_attack_rejected_on_own_turn(self):
        gs, dispatcher = self._combat_setup()
        current = gs.combat.current_combatant_id
        other = next(cid for cid in gs.combat.turn_order if cid != current)
        result = dispatcher.dispatch("opportunity_attack", {
            "attacker_id": current, "target_id": other, "weapon_name": "Longsword",
        })
        assert result["success"] is False

    def test_opportunity_attack_requires_melee(self):
        gs, dispatcher = self._combat_setup()
        attacker, target = self._off_turn_attacker(gs)
        if attacker != "pc1":  # only pc1 carries the bow
            gs.combat.turn_order.reverse()
            attacker, target = self._off_turn_attacker(gs)
        result = dispatcher.dispatch("opportunity_attack", {
            "attacker_id": "pc1", "target_id": target, "weapon_name": "Shortbow",
        })
        assert result["success"] is False


class TestEndCombatGuard:
    def test_end_combat_without_active_combat(self):
        from src.engine.combat import end_combat
        from src.engine.game_state import GameState
        from src.models.world import WorldState

        gs = GameState(
            player_character_ids=["pc1"],
            characters={"pc1": make_char(id="pc1")},
            world=WorldState(current_location_id="loc", locations={}),
        )
        result = end_combat(gs, xp_awarded=100)
        assert result["success"] is False
        assert gs.characters["pc1"].xp == 0  # no phantom XP awarded


class TestTurnScope:
    """A combat render may only resolve the combatant it belongs to."""

    def _setup(self):
        from src.dm.tools import ToolDispatcher
        from src.engine.game_state import GameState
        from src.log.event_log import EventLog
        from src.models.character import Weapon
        from src.models.world import WorldState

        sword = Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")
        chars = {
            "pc1": make_char(id="pc1", name="Aldric", weapons=[sword.model_copy()]),
            "pc2": make_char(id="pc2", name="Zara", weapons=[sword.model_copy()]),
        }
        gs = GameState(
            player_character_ids=["pc1", "pc2"],
            characters=chars,
            world=WorldState(current_location_id="loc", locations={}),
        )
        return gs, ToolDispatcher(gs, EventLog())

    def test_cannot_fast_forward_turns_within_one_render(self):
        """Regression: the LLM chained end_turn calls inside one response,
        skipping monster turns and wrapping the round."""
        gs, dispatcher = self._setup()
        dispatcher.set_turn_scope(None)
        dispatcher.dispatch("start_combat", {"participant_ids": ["pc1", "pc2"]})
        current = gs.combat.current_combatant_id
        other = next(c for c in gs.combat.turn_order if c != current)

        dispatcher.set_turn_scope(current)  # render belongs to `current`
        first = dispatcher.dispatch("end_turn", {})
        assert first["success"] is True
        assert gs.combat.current_combatant_id == other

        # Acting for the next combatant inside the same render is rejected
        atk = dispatcher.dispatch("attack", {
            "attacker_id": other, "target_id": current, "weapon_name": "Longsword",
        })
        assert atk["success"] is False
        assert "prompts their" in atk["error"] or "turn is being resolved" in atk["error"]

        # And so is passing their turn
        second = dispatcher.dispatch("end_turn", {})
        assert second["success"] is False
        assert gs.combat.current_combatant_id == other

    def test_combat_start_locks_render(self):
        """After start_combat in an exploration render, nobody may act until
        the session prompts the first turn."""
        gs, dispatcher = self._setup()
        dispatcher.set_turn_scope("")  # exploration render
        result = dispatcher.dispatch("start_combat", {"participant_ids": ["pc1", "pc2"]})
        assert result["success"] is True
        assert "STOP" in result.get("note", "")

        current = gs.combat.current_combatant_id
        other = next(c for c in gs.combat.turn_order if c != current)
        atk = dispatcher.dispatch("attack", {
            "attacker_id": current, "target_id": other, "weapon_name": "Longsword",
        })
        assert atk["success"] is False
        assert dispatcher.dispatch("end_turn", {})["success"] is False

    def test_none_scope_is_unrestricted(self):
        """API server / scripts (no session) keep full control."""
        gs, dispatcher = self._setup()
        dispatcher.set_turn_scope(None)
        dispatcher.dispatch("start_combat", {"participant_ids": ["pc1", "pc2"]})
        assert dispatcher.dispatch("end_turn", {})["success"] is True
        current = gs.combat.current_combatant_id
        other = next(c for c in gs.combat.turn_order if c != current)
        atk = dispatcher.dispatch("attack", {
            "attacker_id": current, "target_id": other, "weapon_name": "Longsword",
        })
        assert atk["success"] is True

    def test_opportunity_attack_allowed_inside_other_turn_scope(self):
        """Reactions are the one thing another combatant may do off-turn."""
        gs, dispatcher = self._setup()
        dispatcher.set_turn_scope(None)
        dispatcher.dispatch("start_combat", {"participant_ids": ["pc1", "pc2"]})
        current = gs.combat.current_combatant_id
        other = next(c for c in gs.combat.turn_order if c != current)
        dispatcher.set_turn_scope(current)
        oa = dispatcher.dispatch("opportunity_attack", {
            "attacker_id": other, "target_id": current, "weapon_name": "Longsword",
        })
        assert oa["success"] is True


class TestMonsterActionAttack:
    """Monsters attack with any statblock action, using its attack bonus."""

    def _setup(self):
        from src.dm.tools import ToolDispatcher
        from src.engine.game_state import GameState
        from src.log.event_log import EventLog
        from src.models.monster import Monster, MonsterAction
        from src.models.world import WorldState

        wolf = Monster(
            id="wolf_1", name="Wolf", race="Beast", class_name="Monster",
            level=1, hp=11, max_hp=11, ac=13, proficiency_bonus=2,
            hit_dice_remaining=2, hit_die_type="d8",
            ability_scores=AbilityScores(STR=12, DEX=15, CON=12, INT=3, WIS=12, CHA=6),
            actions=[MonsterAction(
                name="Bite", description="Melee Weapon Attack: +4 to hit.",
                action_type="action", attack_bonus=4,
                damage_dice="2d4+2", damage_type="piercing",
            )],
        )
        chars = {"pc1": make_char(id="pc1", name="Aldric"), "wolf_1": wolf}
        gs = GameState(
            player_character_ids=["pc1"],
            characters=chars,
            world=WorldState(current_location_id="loc", locations={}),
        )
        return gs, ToolDispatcher(gs, EventLog())

    def test_statblock_action_used_as_attack(self):
        gs, dispatcher = self._setup()
        result = dispatcher.dispatch("attack", {
            "attacker_id": "wolf_1", "target_id": "pc1", "weapon_name": "Bite",
        })
        assert result["success"] is True
        # Statblock attack bonus, not STR mod + proficiency
        assert result["attack_bonus"] == 4

    def test_unknown_attack_lists_options(self):
        gs, dispatcher = self._setup()
        result = dispatcher.dispatch("attack", {
            "attacker_id": "wolf_1", "target_id": "pc1", "weapon_name": "Tail Slap",
        })
        assert result["success"] is False
        assert "Bite" in result["error"]


class TestReactionSpells:
    """Reaction spells (Shield) may be cast off-turn and consume the reaction."""

    def _setup(self):
        from src.dm.tools import ToolDispatcher
        from src.engine.game_state import GameState
        from src.log.event_log import EventLog
        from src.models.world import WorldState

        mage = make_char(
            id="pc2", name="Zara", class_name="Wizard",
            known_spells=["Shield"], spell_slots={1: 2},
            spellcasting_ability="INT",
        )
        chars = {"pc1": make_char(id="pc1", name="Aldric"), "pc2": mage}
        gs = GameState(
            player_character_ids=["pc1", "pc2"],
            characters=chars,
            world=WorldState(current_location_id="loc", locations={}),
        )
        dispatcher = ToolDispatcher(gs, EventLog())
        dispatcher.dispatch("start_combat", {"participant_ids": ["pc1", "pc2"]})
        # Make pc1 the current combatant; pc2 reacts off-turn
        if gs.combat.current_combatant_id != "pc1":
            from src.engine.combat import end_turn
            end_turn(gs)
        dispatcher.set_turn_scope("pc1")
        return gs, dispatcher

    def test_shield_castable_off_turn(self):
        from src.engine.rules import effective_ac
        gs, dispatcher = self._setup()
        mage = gs.characters["pc2"]
        base_ac = effective_ac(mage)
        result = dispatcher.dispatch("cast_spell", {
            "caster_id": "pc2", "spell_name": "Shield", "target_ids": [],
        })
        assert result["success"] is True
        assert "shielded" in mage.conditions
        assert effective_ac(mage) == base_ac + 5
        assert gs.combat.combatants["pc2"].has_reaction is False
        assert mage.spell_slots[1] == 1

    def test_second_reaction_rejected(self):
        gs, dispatcher = self._setup()
        first = dispatcher.dispatch("cast_spell", {
            "caster_id": "pc2", "spell_name": "Shield", "target_ids": [],
        })
        assert first["success"] is True
        second = dispatcher.dispatch("cast_spell", {
            "caster_id": "pc2", "spell_name": "Shield", "target_ids": [],
        })
        assert second["success"] is False
        assert "reaction" in second["error"]

    def test_shield_expires_after_casters_turn(self):
        from src.engine.combat import end_turn
        gs, dispatcher = self._setup()
        mage = gs.characters["pc2"]
        dispatcher.dispatch("cast_spell", {
            "caster_id": "pc2", "spell_name": "Shield", "target_ids": [],
        })
        assert "shielded" in mage.conditions
        end_turn(gs)  # pc1's turn ends → pc2's turn
        end_turn(gs)  # pc2's turn ends → duration ticks, condition expires
        assert "shielded" not in mage.conditions


class TestSpellAttackUnification:
    """Spell attacks share resolve_attack with weapon attacks."""

    def test_spell_attack_respects_shield_ac(self, monkeypatch):
        from src.engine.spells import resolve_spell
        from src.models.spells import SpellData, SpellResolution
        import src.engine.rules as rules_mod

        caster = make_char(
            id="pc1", name="Aldric", class_name="Wizard",
            spellcasting_ability="INT",
            ability_scores=AbilityScores(STR=10, DEX=10, CON=10, INT=16, WIS=10, CHA=10),
        )
        target = make_char(id="pc2", name="Zara", ac=14, conditions=["shielded"])

        spell = SpellData(
            name="Fire Bolt", level=0, resolution=SpellResolution.ATTACK_ROLL,
            casting_time="action", damage_dice="1d10", damage_type="fire",
            description="A bright streak of flame.",
        )

        # Force a 15 on the d20: hits AC 14, but not AC 19 (14 + Shield's 5)
        real_roll = rules_mod.roll_dice

        def fixed_d20(expr, **kwargs):
            result = real_roll(expr, **kwargs)
            if expr == "1d20":
                object.__setattr__(result, "individual_rolls", [10])
                object.__setattr__(result, "kept_roll", 10)
            return result

        monkeypatch.setattr(rules_mod, "roll_dice", fixed_d20)

        from src.engine.game_state import GameState
        from src.models.world import WorldState
        gs = GameState(
            player_character_ids=["pc1", "pc2"],
            characters={"pc1": caster, "pc2": target},
            world=WorldState(current_location_id="loc", locations={}),
        )
        result = resolve_spell(gs, spell, caster, [target], 0)
        # roll 10 + (3 INT + 2 prof) = 15 < 19 → Shield turned the hit into a miss
        assert result["targets"][0]["hits"] is False


class TestEngineGuards:
    """Guards added after engine-fuzz findings (debug agent, free tier)."""

    def _dispatcher(self):
        from src.dm.tools import ToolDispatcher
        from src.engine.game_state import GameState
        from src.log.event_log import EventLog
        from src.models.world import WorldState

        gs = GameState(
            player_character_ids=["pc1"],
            characters={"pc1": make_char(id="pc1")},
            world=WorldState(current_location_id="loc", locations={}),
        )
        return gs, ToolDispatcher(gs, EventLog())

    def test_negative_healing_rejected(self):
        char = make_char(hp=10)
        result = apply_healing(char, -5)
        assert result["success"] is False
        assert char.hp == 10  # not silently damaged

    def test_healing_the_dead_rejected(self):
        char = make_char(hp=0, conditions=["dead"])
        result = apply_healing(char, 10)
        assert result["success"] is False
        assert char.hp == 0

    def test_bad_dice_expr_clean_error(self):
        gs, dispatcher = self._dispatcher()
        result = dispatcher.dispatch("roll_dice", {"dice_expr": "banana"})
        assert result["success"] is False
        assert not result["error"].startswith("Engine error")

    def test_invalid_ability_clean_error(self):
        gs, dispatcher = self._dispatcher()
        result = dispatcher.dispatch("ability_check", {
            "character_id": "pc1", "ability": "LUCK", "dc": 10,
        })
        assert result["success"] is False
        assert "Valid: STR" in result["error"]

    def test_lowercase_ability_accepted(self):
        gs, dispatcher = self._dispatcher()
        result = dispatcher.dispatch("saving_throw", {
            "character_id": "pc1", "ability": "dex", "dc": 10,
        })
        assert "total" in result
