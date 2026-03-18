#!/usr/bin/env python3
"""QA Debug Agent — CLI entry point.

Plays the game headlessly with an LLM-powered adversarial player,
systematically trying to break each subsystem.

Usage:
    python scripts/debug_agent/run.py
    python scripts/debug_agent/run.py --scenario combat_stress
    python scripts/debug_agent/run.py --provider anthropic --player-provider deepseek
    python scripts/debug_agent/run.py --report reports/qa_run.md
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.debug_agent.harness import HeadlessHarness, TurnResult
from scripts.debug_agent.player_ai import PlayerAI
from scripts.debug_agent.report import Failure, ReportCollector, ScenarioSummary, TurnLog, validate_state
from scripts.debug_agent.scenarios import SCENARIOS, Scenario


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
    p.add_argument("--list", action="store_true", help="List available scenarios and exit")
    return p.parse_args()


def check_result(
    result: TurnResult,
    collector: ReportCollector,
    scenario_name: str,
    turn: int,
    player_input: str,
) -> None:
    """Check a turn result for failures."""
    if not result.ok:
        error_type = "hang" if "timed out" in result.error.lower() else "exception"
        collector.add_failure(Failure(
            scenario=scenario_name,
            turn=turn,
            player_input=player_input,
            error_type=error_type,
            detail=result.error,
            traceback=result.traceback,
            state_snapshot=result.state,
        ))


def run_scenario(
    scenario: Scenario,
    collector: ReportCollector,
    args: argparse.Namespace,
) -> None:
    """Run a single scenario end-to-end."""
    print(f"\n{'='*60}")
    print(f"  Scenario: {scenario.name}")
    print(f"  Personality: {scenario.player_personality}")
    print(f"  Max turns: {scenario.max_turns} (+{len(scenario.setup_actions)} setup)")
    print(f"{'='*60}")

    # Fresh harness per scenario
    harness = HeadlessHarness(
        campaign_path=args.campaign,
        characters_path=args.characters,
        provider=args.provider,
        model=args.model,
    )

    last_narrative = "The adventure begins."
    turn = 0
    turn_log: list[TurnLog] = []
    initial_state = harness._snapshot()
    failures_before = len(collector.failures)
    warnings_before = len(collector.warnings)

    # Phase 1: Scripted setup actions (no LLM player cost)
    for i, action in enumerate(scenario.setup_actions):
        turn = i
        display_input = action[:60] if action else "<empty>"
        print(f"  [setup {i+1}] {display_input}")
        result = harness.step(action, timeout=args.timeout)
        check_result(result, collector, scenario.name, turn, action)

        # Validate state after each turn
        issues = validate_state(harness.game_state)
        for issue in issues:
            collector.add_failure(Failure(
                scenario=scenario.name,
                turn=turn,
                player_input=action,
                error_type="state_inconsistency",
                detail=issue,
                state_snapshot=harness._snapshot(),
            ))

        narrative = result.narrative if result.ok else f"ERROR: {result.error}"
        turn_log.append(TurnLog(turn=i + 1, phase="setup", player_input=action, narrative=narrative, ok=result.ok))

        if result.ok:
            last_narrative = result.narrative
        else:
            print(f"    ERROR: {result.error[:100]}")
            collector.add_warning(scenario.name, f"Setup action {i+1} failed: {result.error[:200]}")

    # Phase 2: AI-driven exploration
    player = PlayerAI(
        scenario=scenario,
        provider=args.player_provider,
        model=args.player_model,
    )

    for ai_turn in range(scenario.max_turns):
        turn = len(scenario.setup_actions) + ai_turn
        state_summary = harness.brief_state()

        try:
            action = player.next_action(ai_turn, last_narrative, state_summary)
        except Exception as e:
            collector.add_warning(scenario.name, f"Player AI failed on turn {ai_turn}: {e}")
            action = "I look around cautiously."

        print(f"  [turn {ai_turn+1}/{scenario.max_turns}] {action[:80]}")

        result = harness.step(action, timeout=args.timeout)
        check_result(result, collector, scenario.name, turn, action)

        # Validate state
        issues = validate_state(harness.game_state)
        for issue in issues:
            collector.add_failure(Failure(
                scenario=scenario.name,
                turn=turn,
                player_input=action,
                error_type="state_inconsistency",
                detail=issue,
                state_snapshot=harness._snapshot(),
            ))

        narrative = result.narrative if result.ok else f"ERROR: {result.error}"
        turn_log.append(TurnLog(turn=ai_turn + 1, phase="ai", player_input=action, narrative=narrative, ok=result.ok))

        if result.ok:
            last_narrative = result.narrative
        else:
            print(f"    ERROR: {result.error[:100]}")
            last_narrative = f"[Error occurred: {result.error[:200]}]"

    collector.record_turns(scenario.name, turn + 1)

    # Check success criteria if defined
    if scenario.success_criteria:
        try:
            passed = scenario.success_criteria(harness.game_state)
            if not passed:
                collector.add_warning(scenario.name, "Success criteria not met at end of scenario")
        except Exception as e:
            collector.add_warning(scenario.name, f"Success criteria check failed: {e}")

    # Record scenario summary
    collector.add_scenario_summary(ScenarioSummary(
        name=scenario.name,
        setup_turns=len(scenario.setup_actions),
        ai_turns=scenario.max_turns,
        initial_state=initial_state,
        final_state=harness._snapshot(),
        turn_log=turn_log,
        failure_count=len(collector.failures) - failures_before,
        warning_count=len(collector.warnings) - warnings_before,
    ))


def main() -> None:
    args = parse_args()

    if args.list:
        print("Available scenarios:\n")
        for name, s in SCENARIOS.items():
            print(f"  {name:25s} {s.max_turns:2d} turns  {s.player_personality}")
        return

    # Select scenarios
    if args.scenario:
        if args.scenario not in SCENARIOS:
            print(f"Unknown scenario: {args.scenario}")
            print(f"Available: {', '.join(SCENARIOS)}")
            sys.exit(1)
        scenarios = [SCENARIOS[args.scenario]]
    else:
        scenarios = list(SCENARIOS.values())

    collector = ReportCollector()
    start_time = time.time()

    print(f"QA Debug Agent — running {len(scenarios)} scenario(s)")
    print(f"DM: {args.provider}/{args.model or 'default'}")
    print(f"Player: {args.player_provider}/{args.player_model or 'default'}")

    report_dir = Path(args.report_dir)
    report_paths: list[Path] = []

    for scenario in scenarios:
        try:
            run_scenario(scenario, collector, args)
        except Exception as e:
            print(f"\n  FATAL ERROR in scenario {scenario.name}: {e}")
            collector.add_failure(Failure(
                scenario=scenario.name,
                turn=-1,
                player_input="<scenario setup>",
                error_type="exception",
                detail=f"Fatal: {e}",
                traceback=__import__("traceback").format_exc(),
            ))
            collector.record_turns(scenario.name, 0)
        # Write after each scenario so partial results survive Ctrl+C
        rp = collector.write_scenario_report(scenario.name, report_dir)
        report_paths.append(rp)
        print(f"  Report written: {rp}")

    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Failures: {len(collector.failures)}")
    print(f"  Warnings: {len(collector.warnings)}")
    print(f"  Reports: {report_dir}/")
    for rp in report_paths:
        print(f"    {rp.name}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
