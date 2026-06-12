"""Wiring tests for the QA debug agent (scripts/debug_agent).

The engine tier runs for real (it is free); the DM tier runs against a stub
harness so no LLM calls are made.
"""
from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest

from scripts.debug_agent.engine_scenarios import ENGINE_SCENARIOS, EngineCtx
from scripts.debug_agent.harness import EngineHarness, TurnResult
from scripts.debug_agent.report import ReportCollector
from scripts.debug_agent.scenarios import SCENARIOS, Scenario


def _args(**overrides) -> Namespace:
    defaults = dict(
        campaign="campaigns/shattered_crown.json", characters=None,
        provider="deepseek", model=None,
        player_provider="deepseek", player_model=None,
        timeout=5.0, no_session_emulation=False, max_monster_turns=4,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


class TestEngineScenarios:
    """All free engine scenarios must pass against the current engine."""

    @pytest.mark.parametrize("name", list(ENGINE_SCENARIOS))
    def test_engine_scenario_green(self, name):
        scenario = ENGINE_SCENARIOS[name]
        harness = EngineHarness(seed=scenario.seed)
        collector = ReportCollector()
        ctx = EngineCtx(harness, collector, name)
        scenario.script(ctx)
        details = [f"{f.error_type}: {f.detail}" for f in collector.failures]
        assert not collector.failures, f"{name} found regressions: {details}"


class _StubHarness:
    """Real GameState + ToolDispatcher, no LLM. step() is a no-op narration."""

    def __init__(self, **_kwargs):
        engine = EngineHarness(seed=7)
        self.game_state = engine.game_state
        self.event_log = engine.event_log
        self.dm = SimpleNamespace(
            tool_dispatcher=engine.dispatcher,
            token_stats=SimpleNamespace(api_calls=0, estimated_cost_usd=0.0),
        )
        self.steps: list[tuple[str, str | None]] = []

    def step(self, player_input, timeout=120.0, turn_scope=None):
        self.dm.tool_dispatcher.set_turn_scope(turn_scope)
        self.steps.append((player_input, turn_scope))
        return TurnResult(ok=True, narrative="(stub narration)", state=self._snapshot())

    def _snapshot(self):
        return {"location": "stub", "combat_active": self.game_state.combat.active}

    def brief_state(self):
        return "stub state"


class TestRunScenarioWiring:
    def test_scripted_scenario_with_stub_dm(self, monkeypatch):
        import scripts.debug_agent.run as run_mod

        stub_holder = {}

        def make_stub(**kwargs):
            stub_holder["h"] = _StubHarness(**kwargs)
            return stub_holder["h"]

        monkeypatch.setattr(run_mod, "HeadlessHarness", make_stub)
        scenario = Scenario(
            name="wiring_test", kind="scripted", description="",
            player_personality="(scripted)", max_turns=0,
            setup_actions=["look around", "open the door"],
        )
        collector = ReportCollector()
        run_mod.run_scenario(scenario, collector, _args())

        assert not collector.failures
        summary = collector.scenario_summaries["wiring_test"]
        assert summary.kind == "scripted"
        assert len(summary.turn_log) == 2
        # Exploration renders carry the locked scope, like the CLI session
        assert stub_holder["h"].steps == [("look around", ""), ("open the door", "")]

    def test_monster_turn_emulation_advances_combat(self, monkeypatch):
        """With combat active and a monster up, the runner prompts monster
        turns (scoped) and force-advances stalled ones until a PC is up."""
        import scripts.debug_agent.run as run_mod

        stub_holder = {}

        def make_stub(**kwargs):
            h = _StubHarness(**kwargs)
            # Start combat with two wolves; rotate until a wolf is up
            h.dm.tool_dispatcher.set_turn_scope(None)
            h.dm.tool_dispatcher.dispatch("start_combat", {
                "participant_ids": ["aldric", "zara"],
                "monster_templates": ["wolf", "wolf"],
            })
            from src.engine.combat import end_turn
            gs = h.game_state
            for _ in range(4):
                if gs.characters[gs.combat.current_combatant_id].is_player:
                    end_turn(gs)
                else:
                    break
            stub_holder["h"] = h
            return h

        monkeypatch.setattr(run_mod, "HeadlessHarness", make_stub)
        scenario = Scenario(
            name="emulation_test", kind="scripted", description="",
            player_personality="(scripted)", max_turns=0,
            setup_actions=["attack the wolf"],
        )
        collector = ReportCollector()
        run_mod.run_scenario(scenario, collector, _args())

        h = stub_holder["h"]
        gs = h.game_state
        # The stub DM never calls end_turn, so the runner's stall handling
        # must have advanced past the monsters to a player character
        assert gs.characters[gs.combat.current_combatant_id].is_player
        # Monster prompts were issued with the monster's id as scope
        monster_steps = [(inp, scope) for inp, scope in h.steps if "It is" in inp]
        assert monster_steps, "no monster-turn prompts were sent"
        assert all(scope and scope.startswith("wolf") for _, scope in monster_steps)
        assert not collector.failures


class TestScenarioDefinitions:
    def test_kinds_are_valid(self):
        assert all(s.kind in ("ai", "scripted") for s in SCENARIOS.values())

    def test_scripted_scenarios_have_inputs_and_no_ai_turns(self):
        for s in SCENARIOS.values():
            if s.kind == "scripted":
                assert s.setup_actions, f"{s.name}: scripted scenario without inputs"
                assert s.max_turns == 0, f"{s.name}: scripted scenario with AI turns"

    def test_no_name_collisions_with_engine_tier(self):
        assert not set(SCENARIOS) & set(ENGINE_SCENARIOS)
