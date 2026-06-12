#!/usr/bin/env python3
"""QA Debug Agent — CLI entry point.

Plays the game headlessly and systematically tries to break each subsystem.
Three scenario tiers, ordered by cost:

  engine    — drives the ToolDispatcher directly. No LLM, no API key, free.
  scripted  — fixed player-input lists against the LLM DM. DM cost only.
  ai        — adversarial LLM player vs. LLM DM. Most expensive, most creative.

Usage:
    python scripts/debug_agent/run.py --list
    python scripts/debug_agent/run.py --free            # engine tier only (no key)
    python scripts/debug_agent/run.py --cheap           # engine + scripted
    python scripts/debug_agent/run.py                   # everything
    python scripts/debug_agent/run.py --scenario combat_stress
    python scripts/debug_agent/run.py --provider anthropic --player-provider deepseek
    python scripts/debug_agent/run.py --report-dir reports
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback as tb_module
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.debug_agent.engine_scenarios import ENGINE_SCENARIOS, EngineCtx, EngineScenario
from scripts.debug_agent.harness import EngineHarness, HeadlessHarness, TurnResult
from scripts.debug_agent.player_ai import PlayerAI
from scripts.debug_agent.report import Failure, ReportCollector, ScenarioSummary, TurnLog, validate_state
from scripts.debug_agent.scenarios import SCENARIOS, Scenario

# Session emulation: prompt sent for each monster turn (mirrors session.py)
_MONSTER_TURN_PROMPT = (
    "[DM: It is {name}'s turn. Call get_monster_actions('{mid}') first, "
    "then resolve their actions, then call end_turn().]"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="QA Debug Agent")
    p.add_argument("--scenario", default=None, help="Run a single scenario (default: all)")
    p.add_argument("--campaign", default="campaigns/shattered_crown.json", help="Campaign file")
    p.add_argument("--characters", default=None, help="Characters JSON file")
    p.add_argument("--provider", default="deepseek", help="LLM provider for the DM (default: deepseek)")
    p.add_argument("--model", default=None, help="Model override for the DM")
    p.add_argument("--player-provider", default="deepseek", help="LLM provider for player AI (default: deepseek)")
    p.add_argument("--player-model", default=None, help="Model override for player AI")
    p.add_argument("--report-dir", default="reports", help="Directory for per-scenario report files")
    p.add_argument("--timeout", type=float, default=120.0, help="Per-turn timeout in seconds")
    p.add_argument("--free", action="store_true", help="Run only the free engine tier (no API key needed)")
    p.add_argument("--cheap", action="store_true", help="Run engine + scripted tiers (no player AI cost)")
    p.add_argument("--max-monster-turns", type=int, default=4,
                   help="Cap on LLM-driven monster turns per player input (cost bound, default 4)")
    p.add_argument("--no-session-emulation", action="store_true",
                   help="Legacy mode: unrestricted turn scope, no per-turn monster prompts")
    p.add_argument("--list", action="store_true", help="List available scenarios and exit")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Engine tier (free)
# ---------------------------------------------------------------------------

def run_engine_scenario(
    scenario: EngineScenario,
    collector: ReportCollector,
    args: argparse.Namespace,
) -> None:
    print(f"\n{'='*60}")
    print(f"  Scenario: {scenario.name}  [engine — free]")
    print(f"{'='*60}")

    failures_before = len(collector.failures)
    warnings_before = len(collector.warnings)

    harness = EngineHarness(
        campaign_path=args.campaign,
        characters_path=args.characters,
        seed=scenario.seed,
    )
    ctx = EngineCtx(harness, collector, scenario.name)
    initial_state = _snapshot_engine(harness)

    try:
        scenario.script(ctx)
    except Exception as e:
        collector.add_failure(Failure(
            scenario=scenario.name, turn=ctx.step_num,
            player_input="<scenario script>", error_type="exception",
            detail=f"Script crashed: {e}", traceback=tb_module.format_exc(),
        ))

    n_fail = len(collector.failures) - failures_before
    print(f"  {ctx.step_num} engine calls, {n_fail} failure(s)")

    collector.record_turns(scenario.name, ctx.step_num)
    collector.add_scenario_summary(ScenarioSummary(
        name=scenario.name, kind="engine",
        setup_turns=ctx.step_num, ai_turns=0,
        initial_state=initial_state, final_state=_snapshot_engine(harness),
        turn_log=ctx.turn_log,
        failure_count=n_fail,
        warning_count=len(collector.warnings) - warnings_before,
    ))


def _snapshot_engine(harness: EngineHarness) -> dict:
    gs = harness.game_state
    return {
        "location": gs.world.current_location_id,
        "combat_active": gs.combat.active,
        "hp_summary": {c.name: f"{c.hp}/{c.max_hp}"
                       for c in gs.characters.values() if c.is_player},
    }


# ---------------------------------------------------------------------------
# DM tiers (scripted / ai)
# ---------------------------------------------------------------------------

def run_scenario(
    scenario: Scenario,
    collector: ReportCollector,
    args: argparse.Namespace,
) -> None:
    """Run a scripted or AI scenario end-to-end."""
    print(f"\n{'='*60}")
    print(f"  Scenario: {scenario.name}  [{scenario.kind}]")
    if scenario.kind == "ai":
        print(f"  Personality: {scenario.player_personality}")
    print(f"  Max turns: {scenario.max_turns} (+{len(scenario.setup_actions)} setup)")
    print(f"{'='*60}")

    harness = HeadlessHarness(
        campaign_path=args.campaign,
        characters_path=args.characters,
        provider=args.provider,
        model=args.model,
    )

    emulate = not args.no_session_emulation
    state = {"last_narrative": "The adventure begins.", "turn": 0, "player_calls": 0}
    turn_log: list[TurnLog] = []
    initial_state = harness._snapshot()
    failures_before = len(collector.failures)
    warnings_before = len(collector.warnings)

    def check(result: TurnResult, player_input: str) -> None:
        if not result.ok:
            error_type = "hang" if "timed out" in result.error.lower() else "exception"
            collector.add_failure(Failure(
                scenario=scenario.name, turn=state["turn"],
                player_input=player_input, error_type=error_type,
                detail=result.error, traceback=result.traceback,
                state_snapshot=result.state,
            ))
        for issue in validate_state(harness.game_state):
            collector.add_failure(Failure(
                scenario=scenario.name, turn=state["turn"],
                player_input=player_input, error_type="state_inconsistency",
                detail=issue, state_snapshot=harness._snapshot(),
            ))

    def do_turn(phase: str, display_turn: int, action: str) -> None:
        """One player input + (if emulating) the monster turns that follow."""
        gs = harness.game_state
        scope = gs.combat.current_combatant_id if (emulate and gs.combat.active) else ("" if emulate else None)
        result = harness.step(action, timeout=args.timeout, turn_scope=scope)
        check(result, action)
        narrative = result.narrative if result.ok else f"ERROR: {result.error}"
        turn_log.append(TurnLog(turn=display_turn, phase=phase,
                                player_input=action, narrative=narrative, ok=result.ok))
        if result.ok:
            state["last_narrative"] = result.narrative
        else:
            print(f"    ERROR: {result.error[:100]}")
            state["last_narrative"] = f"[Error occurred: {result.error[:200]}]"

        if not emulate:
            return

        # Session emulation: resolve non-player turns until a PC is up again.
        monster_turns = 0
        while gs.combat.active:
            cur = gs.combat.current_combatant_id
            char = gs.characters.get(cur)
            dispatcher = harness.dm.tool_dispatcher
            if char is None or "dead" in char.conditions or (not char.is_player and char.hp <= 0):
                from src.engine.combat import end_turn
                end_turn(gs)  # session auto-skip (engine-level, free)
                continue
            if char.is_player and char.hp <= 0:
                # Dying PC: auto death save + end turn (free, mirrors session)
                dispatcher.set_turn_scope(cur)
                if "stable" not in char.conditions:
                    dispatcher.dispatch("death_save", {"character_id": cur})
                dispatcher.dispatch("end_turn", {})
                continue
            if char.is_player:
                break  # next player input handles this
            if monster_turns >= args.max_monster_turns:
                collector.add_warning(
                    scenario.name,
                    f"Monster-turn cap ({args.max_monster_turns}) hit after input "
                    f"{display_turn!r} — combat continues next input",
                )
                break
            monster_turns += 1
            prompt = _MONSTER_TURN_PROMPT.format(name=char.name, mid=cur)
            print(f"    [monster turn] {char.name}")
            m_result = harness.step(prompt, timeout=args.timeout, turn_scope=cur)
            check(m_result, prompt)
            turn_log.append(TurnLog(turn=display_turn, phase=f"{phase}/monster",
                                    player_input=f"<{char.name}'s turn>",
                                    narrative=m_result.narrative if m_result.ok
                                    else f"ERROR: {m_result.error}", ok=m_result.ok))
            if gs.combat.active and gs.combat.current_combatant_id == cur:
                # Stalled monster turn — force advance, like the session does
                dispatcher.set_turn_scope(cur)
                dispatcher.dispatch("end_turn", {})

    # Phase 1: scripted setup actions (no player-LLM cost)
    for i, action in enumerate(scenario.setup_actions):
        state["turn"] = i
        print(f"  [setup {i+1}] {(action[:60] or '<empty>')}")
        do_turn("setup", i + 1, action)

    # Phase 2: AI-driven exploration (skipped entirely for scripted scenarios)
    if scenario.kind == "ai" and scenario.max_turns > 0:
        player = PlayerAI(
            scenario=scenario,
            provider=args.player_provider,
            model=args.player_model,
        )
        for ai_turn in range(scenario.max_turns):
            state["turn"] = len(scenario.setup_actions) + ai_turn
            try:
                action = player.next_action(ai_turn, state["last_narrative"], harness.brief_state())
                state["player_calls"] += 1
            except Exception as e:
                collector.add_warning(scenario.name, f"Player AI failed on turn {ai_turn}: {e}")
                action = "I look around cautiously."
            print(f"  [turn {ai_turn+1}/{scenario.max_turns}] {action[:80]}")
            do_turn("ai", ai_turn + 1, action)

    collector.record_turns(scenario.name, state["turn"] + 1)

    # Success criteria
    if scenario.success_criteria:
        try:
            if not scenario.success_criteria(harness.game_state):
                collector.add_warning(scenario.name, "Success criteria not met at end of scenario")
        except Exception as e:
            collector.add_warning(scenario.name, f"Success criteria check failed: {e}")

    stats = harness.dm.token_stats
    collector.add_scenario_summary(ScenarioSummary(
        name=scenario.name, kind=scenario.kind,
        setup_turns=len(scenario.setup_actions),
        ai_turns=scenario.max_turns if scenario.kind == "ai" else 0,
        initial_state=initial_state,
        final_state=harness._snapshot(),
        turn_log=turn_log,
        failure_count=len(collector.failures) - failures_before,
        warning_count=len(collector.warnings) - warnings_before,
        dm_calls=stats.api_calls,
        player_calls=state["player_calls"],
        cost_usd=stats.estimated_cost_usd,
    ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.list:
        print("Available scenarios:\n")
        print("  -- engine (free, no API key) --")
        for name, es in ENGINE_SCENARIOS.items():
            print(f"  {name:25s} {es.description}")
        print("\n  -- scripted (DM cost only) --")
        for name, s in SCENARIOS.items():
            if s.kind == "scripted":
                print(f"  {name:25s} {len(s.setup_actions):2d} inputs  {s.description[:70]}")
        print("\n  -- ai (DM + player cost) --")
        for name, s in SCENARIOS.items():
            if s.kind == "ai":
                print(f"  {name:25s} {s.max_turns:2d} turns  {s.player_personality}")
        return

    # Select scenarios
    engine_scenarios: list[EngineScenario] = []
    dm_scenarios: list[Scenario] = []
    if args.scenario:
        if args.scenario in ENGINE_SCENARIOS:
            engine_scenarios = [ENGINE_SCENARIOS[args.scenario]]
        elif args.scenario in SCENARIOS:
            dm_scenarios = [SCENARIOS[args.scenario]]
        else:
            print(f"Unknown scenario: {args.scenario}")
            print(f"Available: {', '.join([*ENGINE_SCENARIOS, *SCENARIOS])}")
            sys.exit(1)
    else:
        engine_scenarios = list(ENGINE_SCENARIOS.values())
        if not args.free:
            dm_scenarios = [s for s in SCENARIOS.values()
                            if not (args.cheap and s.kind == "ai")]

    collector = ReportCollector()
    start_time = time.time()

    n_total = len(engine_scenarios) + len(dm_scenarios)
    print(f"QA Debug Agent — running {n_total} scenario(s)")
    if dm_scenarios:
        print(f"DM: {args.provider}/{args.model or 'default'}")
        if any(s.kind == "ai" for s in dm_scenarios):
            print(f"Player: {args.player_provider}/{args.player_model or 'default'}")

    report_dir = Path(args.report_dir)
    report_paths: list[Path] = []
    total_cost = 0.0

    for es in engine_scenarios:
        try:
            run_engine_scenario(es, collector, args)
        except Exception as e:
            print(f"\n  FATAL ERROR in scenario {es.name}: {e}")
            collector.add_failure(Failure(
                scenario=es.name, turn=-1, player_input="<scenario setup>",
                error_type="exception", detail=f"Fatal: {e}",
                traceback=tb_module.format_exc(),
            ))
        rp = collector.write_scenario_report(es.name, report_dir)
        report_paths.append(rp)
        print(f"  Report written: {rp}")

    for scenario in dm_scenarios:
        try:
            run_scenario(scenario, collector, args)
        except Exception as e:
            print(f"\n  FATAL ERROR in scenario {scenario.name}: {e}")
            collector.add_failure(Failure(
                scenario=scenario.name, turn=-1, player_input="<scenario setup>",
                error_type="exception", detail=f"Fatal: {e}",
                traceback=tb_module.format_exc(),
            ))
            collector.record_turns(scenario.name, 0)
        summary = collector.scenario_summaries.get(scenario.name)
        if summary:
            total_cost += summary.cost_usd
        # Write after each scenario so partial results survive Ctrl+C
        rp = collector.write_scenario_report(scenario.name, report_dir)
        report_paths.append(rp)
        print(f"  Report written: {rp}")

    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Failures: {len(collector.failures)}")
    print(f"  Warnings: {len(collector.warnings)}")
    if total_cost:
        print(f"  Estimated DM-side cost: ${total_cost:.4f}")
    print(f"  Reports: {report_dir}/")
    for rp in report_paths:
        print(f"    {rp.name}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
