"""Failure collector and markdown report writer."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.game_state import GameState


@dataclass
class Failure:
    scenario: str
    turn: int
    player_input: str
    error_type: str  # "exception", "state_inconsistency", "tool_error", "hang"
    detail: str
    traceback: str | None = None
    state_snapshot: dict = field(default_factory=dict)


@dataclass
class Warning:
    scenario: str
    message: str


@dataclass
class TurnLog:
    turn: int
    phase: str  # "setup" or "ai"
    player_input: str
    narrative: str  # full DM output or error message
    ok: bool


@dataclass
class ScenarioSummary:
    name: str
    setup_turns: int
    ai_turns: int
    initial_state: dict = field(default_factory=dict)
    final_state: dict = field(default_factory=dict)
    turn_log: list[TurnLog] = field(default_factory=list)
    failure_count: int = 0
    warning_count: int = 0


class ReportCollector:
    def __init__(self) -> None:
        self.failures: list[Failure] = []
        self.warnings: list[Warning] = []
        self.scenario_turns: dict[str, int] = {}
        self.scenario_summaries: dict[str, ScenarioSummary] = {}

    def add_failure(self, failure: Failure) -> None:
        self.failures.append(failure)

    def add_warning(self, scenario: str, message: str) -> None:
        self.warnings.append(Warning(scenario=scenario, message=message))

    def record_turns(self, scenario: str, turns: int) -> None:
        self.scenario_turns[scenario] = turns

    def add_scenario_summary(self, summary: ScenarioSummary) -> None:
        self.scenario_summaries[summary.name] = summary

    def write_scenario_report(self, scenario_name: str, report_dir: Path) -> Path:
        """Write/append a single scenario's results to reports/<scenario_name>.md."""
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"{scenario_name}.md"

        severity_order = {"exception": 0, "hang": 1, "state_inconsistency": 2, "tool_error": 3}

        # Filter failures/warnings for this scenario
        scenario_failures = sorted(
            [f for f in self.failures if f.scenario == scenario_name],
            key=lambda f: (severity_order.get(f.error_type, 99), f.turn),
        )
        scenario_warnings = [w for w in self.warnings if w.scenario == scenario_name]
        summary = self.scenario_summaries.get(scenario_name)

        lines: list[str] = []

        # If file doesn't exist, write the header
        if not path.exists():
            lines.append(f"# {scenario_name}\n")

        # Run separator with timestamp
        from datetime import datetime
        lines.append(f"---\n\n## Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        n_fail = len(scenario_failures)
        n_warn = len(scenario_warnings)
        status = "PASS" if n_fail == 0 else f"FAIL ({n_fail})"
        lines.append(f"**Status:** {status}  ")
        lines.append(f"**Failures:** {n_fail}  ")
        lines.append(f"**Warnings:** {n_warn}\n")

        # Scenario summary
        if summary:
            lines.append(f"Turns: {summary.setup_turns} setup + {summary.ai_turns} AI = {summary.setup_turns + summary.ai_turns} total  ")

            if summary.initial_state and summary.final_state:
                lines.append(f"Initial: `{_brief_snapshot(summary.initial_state)}`  ")
                lines.append(f"Final: `{_brief_snapshot(summary.final_state)}`\n")

            # Turn log
            if summary.turn_log:
                lines.append("<details><summary>Turn log</summary>\n")
                for t in summary.turn_log:
                    icon = "+" if t.ok else "x"
                    inp = t.player_input or "<empty>"
                    lines.append(f"#### [{icon}] {t.phase} {t.turn}\n")
                    lines.append(f"**Input:** {inp}\n")
                    lines.append(f"**Output:**\n{t.narrative}\n")
                lines.append("</details>\n")

        # Failures
        if scenario_failures:
            lines.append("### Failures\n")
            for f in scenario_failures:
                lines.append(f"**Turn {f.turn}** — `{f.error_type}`  ")
                lines.append(f"Input: `{f.player_input[:100]}`  ")
                lines.append(f"Detail: {f.detail}  ")
                if f.traceback:
                    lines.append("<details><summary>Traceback</summary>\n")
                    lines.append(f"```\n{f.traceback}\n```\n")
                    lines.append("</details>\n")
                if f.state_snapshot:
                    lines.append(f"State: `{_brief_snapshot(f.state_snapshot)}`\n")

        # Warnings
        if scenario_warnings:
            lines.append("### Warnings\n")
            for w in scenario_warnings:
                lines.append(f"- {w.message}")
            lines.append("")

        # Append to file
        with open(path, "a") as fh:
            fh.write("\n".join(lines) + "\n")

        return path


def _brief_snapshot(snap: dict) -> str:
    """One-line summary of state snapshot."""
    parts = []
    for key in ("location", "combat_active", "hp_summary"):
        if key in snap:
            parts.append(f"{key}={snap[key]}")
    return ", ".join(parts) if parts else str(snap)[:120]


def validate_state(gs: "GameState") -> list[str]:
    """Return list of state inconsistency descriptions."""
    issues: list[str] = []

    for cid, char in gs.characters.items():
        # HP range
        if char.hp < 0:
            issues.append(f"{char.name} ({cid}) has negative HP: {char.hp}")
        if char.hp > char.max_hp + char.temp_hp:
            issues.append(f"{char.name} ({cid}) HP {char.hp} exceeds max {char.max_hp} + temp {char.temp_hp}")

        # Spell slots non-negative
        for level, slots in char.spell_slots.items():
            if slots < 0:
                issues.append(f"{char.name} ({cid}) has negative spell slots at level {level}: {slots}")
            max_slots = char.max_spell_slots.get(level, 0)
            if slots > max_slots:
                issues.append(f"{char.name} ({cid}) spell slots level {level}: {slots} > max {max_slots}")

        # Death saves range
        if char.death_saves.successes < 0 or char.death_saves.successes > 3:
            issues.append(f"{char.name} ({cid}) death save successes out of range: {char.death_saves.successes}")
        if char.death_saves.failures < 0 or char.death_saves.failures > 3:
            issues.append(f"{char.name} ({cid}) death save failures out of range: {char.death_saves.failures}")

        # Dead character in combat turn order
        if char.hp <= 0 and not char.is_player and gs.combat.active:
            if cid in gs.combat.turn_order:
                issues.append(f"Dead NPC/monster {char.name} ({cid}) still in combat turn order")

    # Combat state consistency
    if gs.combat.active:
        for cid in gs.combat.turn_order:
            if cid not in gs.characters and cid not in gs.combat.combatants:
                issues.append(f"Turn order references unknown character: {cid}")
        if gs.combat.current_turn_index >= len(gs.combat.turn_order) and gs.combat.turn_order:
            issues.append(
                f"Current turn index {gs.combat.current_turn_index} "
                f"out of bounds for turn order (len={len(gs.combat.turn_order)})"
            )
        # Duplicate initiative entries
        if len(gs.combat.turn_order) != len(set(gs.combat.turn_order)):
            seen = set()
            dupes = [x for x in gs.combat.turn_order if x in seen or seen.add(x)]  # type: ignore[func-returns-value]
            issues.append(f"Duplicate entries in turn order: {dupes}")

    # Current location exists
    if gs.world.current_location_id not in gs.world.locations:
        issues.append(f"Current location '{gs.world.current_location_id}' not in world locations")

    return issues
