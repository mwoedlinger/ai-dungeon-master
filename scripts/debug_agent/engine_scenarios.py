"""LLM-free engine scenarios — fuzz the ToolDispatcher/rules engine directly.

These cost nothing to run (no API key needed) and are fully deterministic
(seeded RNG), so they can run on every change like a slow integration test.

Each scenario is a function driving an EngineCtx:
    ctx.call(tool, inputs, expect=True/False/None)  — dispatch + verdict
    ctx.scope(combatant_id)                          — emulate session turn scope
    ctx.check(condition, detail)                     — direct state assertion
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from scripts.debug_agent.report import Failure, ReportCollector, TurnLog, validate_state

if TYPE_CHECKING:
    from scripts.debug_agent.harness import EngineHarness

# Exception types that indicate a *designed* rejection path when they appear
# in an "Engine error:" message (e.g. dice parse errors). Anything else that
# bubbles up as "Engine error" is an unhandled-exception finding.
_TOLERATED_ERROR_TYPES = ("ValueError", "KeyError")


class EngineCtx:
    def __init__(self, harness: "EngineHarness", collector: ReportCollector, scenario: str):
        self.harness = harness
        self.collector = collector
        self.scenario = scenario
        self.step_num = 0
        self.turn_log: list[TurnLog] = []
        self._seen_state_issues: set[str] = set()

    @property
    def gs(self):
        return self.harness.game_state

    def scope(self, combatant_id: str | None) -> None:
        self.harness.dispatcher.set_turn_scope(combatant_id)

    def current(self) -> str:
        return self.gs.combat.current_combatant_id

    def call(self, tool: str, inputs: dict, expect: bool | None = None, note: str = "") -> dict:
        """Dispatch a tool call and record verdicts.

        expect=True  — must succeed; failure or engine crash is a finding.
        expect=False — must be rejected; success means a guard is missing.
        expect=None  — exploratory; only crashes and state corruption count.
        """
        self.step_num = self.step_num + 1
        result = self.harness.dispatcher.dispatch(tool, inputs)
        ok = result.get("success", True) is not False
        err = result.get("error", "") or ""

        # Unhandled exceptions surface as "Engine error: <Type>: ..."
        if isinstance(err, str) and err.startswith("Engine error:"):
            exc_type = err.split(":", 2)[1].strip() if ":" in err[13:] else ""
            if expect is False and exc_type in _TOLERATED_ERROR_TYPES:
                # Rejected, but via a raw exception rather than a clean error
                self.collector.add_warning(
                    self.scenario,
                    f"Step {self.step_num} {tool}: rejected via raw {exc_type} "
                    f"instead of a clean error message ({err[:120]})",
                )
            else:
                self._fail("exception", tool, inputs, f"Unhandled engine exception: {err}")
        elif expect is True and not ok:
            self._fail("tool_error", tool, inputs,
                       f"Expected success but got: {err[:200]}{note and f' ({note})'}")
        elif expect is False and ok:
            self._fail("tool_error", tool, inputs,
                       f"Expected rejection but call succeeded{note and f' ({note})'}")

        # State validation — report each distinct issue once per scenario
        for issue in validate_state(self.gs):
            if issue not in self._seen_state_issues:
                self._seen_state_issues.add(issue)
                self._fail("state_inconsistency", tool, inputs, issue)

        verdict = "ok" if ok else f"rejected: {err[:100]}"
        self.turn_log.append(TurnLog(
            turn=self.step_num, phase="engine",
            player_input=f"{tool}({_brief_inputs(inputs)})",
            narrative=verdict, ok=ok if expect is not False else True,
        ))
        return result

    def check(self, condition: bool, detail: str) -> None:
        """Direct state assertion."""
        if not condition:
            self._fail("state_inconsistency", "<check>", {}, detail)

    def _fail(self, error_type: str, tool: str, inputs: dict, detail: str) -> None:
        self.collector.add_failure(Failure(
            scenario=self.scenario, turn=self.step_num,
            player_input=f"{tool}({_brief_inputs(inputs)})",
            error_type=error_type, detail=detail,
        ))


def _brief_inputs(inputs: dict) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in inputs.items())
    return s[:120]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def _guard_fuzz(ctx: EngineCtx) -> None:
    """Every guard the dispatcher/engine promises must hold."""
    ctx.call("nonexistent_tool", {}, expect=False)
    ctx.call("attack", {"attacker_id": "nobody", "target_id": "aldric",
                        "weapon_name": "Longsword"}, expect=False)
    ctx.call("attack", {"attacker_id": "aldric", "target_id": "zara",
                        "weapon_name": "Excalibur"}, expect=False, note="unknown weapon")
    ctx.call("apply_damage", {"target_id": "aldric", "amount": -10,
                              "damage_type": "fire"}, expect=False)
    ctx.call("apply_healing", {"target_id": "aldric", "amount": -10}, expect=False)
    ctx.call("cast_spell", {"caster_id": "zara", "spell_name": "Summon Tarrasque",
                            "target_ids": []}, expect=False)
    ctx.call("cast_spell", {"caster_id": "zara", "spell_name": "Fireball",
                            "target_ids": ["aldric"], "spell_level": 1},
             expect=False, note="upcast validation: level-3 spell with level-1 slot")
    ctx.call("cast_spell", {"caster_id": "aldric", "spell_name": "Fireball",
                            "target_ids": ["zara"]}, expect=False,
             note="fighter doesn't know Fireball")
    ctx.call("ability_check", {"character_id": "aldric", "ability": "LUCK",
                               "dc": 10}, expect=False, note="invalid ability")
    ctx.call("saving_throw", {"character_id": "aldric", "ability": "SWAG",
                              "dc": 10}, expect=False, note="invalid ability")
    # Note: for checks, "success" is the check outcome (vs DC), not tool-ok —
    # so only assert the roll resolved, not that it passed.
    res = ctx.call("ability_check", {"character_id": "aldric", "ability": "str",
                                     "dc": 10}, expect=None, note="lowercase ability ok")
    ctx.check("total" in res, "lowercase ability name was not accepted")
    ctx.call("end_turn", {}, expect=False, note="no combat active")
    ctx.call("end_combat", {"xp_awarded": 500}, expect=False, note="no combat active")
    ctx.call("death_save", {"character_id": "aldric"}, expect=False,
             note="not unconscious")
    ctx.call("attune_item", {"character_id": "aldric", "item_name": "Ring of Wishes",
                             "item_type": "ring", "bonus": 3}, expect=False,
             note="item not in inventory")
    ctx.call("remove_item", {"character_id": "aldric", "item_name": "Moon Cheese",
                             "quantity": 3}, expect=False)
    ctx.call("use_lay_on_hands", {"character_id": "aldric", "target_id": "zara",
                                  "amount": 10}, expect=False,
             note="fighter has no Lay on Hands pool")
    # Dead characters: no healing, no long-rest resurrection
    zara = ctx.gs.characters["zara"]
    zara.hp = 0
    zara.conditions.append("dead")
    ctx.call("apply_healing", {"target_id": "zara", "amount": 10}, expect=False,
             note="healing the dead")
    ctx.call("take_long_rest", {"character_id": "zara"}, expect=False,
             note="long rest while dead")
    zara.conditions.remove("dead")
    zara.hp = zara.max_hp


def _dice_fuzz(ctx: EngineCtx) -> None:
    """Dice expressions: valid forms succeed, garbage is rejected without crashing."""
    for expr in ("1d20", "2d6+3", "4d6kh3", "4d6kh3+2", "1d8-1", "d20", "10d10"):
        ctx.call("roll_dice", {"dice_expr": expr}, expect=True)
    for expr in ("", "banana", "d", "1d", "20", "1d6+", "-1d6", "1d6 fire", "🎲"):
        ctx.call("roll_dice", {"dice_expr": expr}, expect=False)
    # Large but bounded rolls must not hang
    ctx.call("roll_dice", {"dice_expr": "1000d6"}, expect=None)


def _combat_cycle(ctx: EngineCtx) -> None:
    """Full combat lifecycle under session-style turn scope.

    Covers: start lock, re-entry guard, statblock attacks, turn-scope
    fast-forward rejection, opportunity attacks, reaction spells (Shield),
    dying/death-save flow, and end_combat cleanup.
    """
    gs = ctx.gs

    # Exploration render: combat starts and locks the render
    ctx.scope("")
    ctx.call("start_combat", {"participant_ids": ["aldric", "zara"],
                              "monster_templates": ["wolf", "wolf"]}, expect=True)
    ctx.check(gs.combat.active and len(gs.combat.turn_order) == 4,
              "start_combat: expected 4 combatants")
    ctx.call("attack", {"attacker_id": ctx.current(), "target_id": "wolf_1",
                        "weapon_name": "Longsword"}, expect=False,
             note="locked render after start_combat")
    ctx.call("start_combat", {"participant_ids": ["aldric", "zara"],
                              "monster_templates": ["wolf"]}, expect=False,
             note="re-entry guard")
    ctx.check("wolf_3" not in gs.characters, "re-entry guard: duplicate wolf spawned")

    # Play two full rounds the way the session does: one scoped render per turn
    shield_cast = oa_done = False
    for _ in range(8):
        if not gs.combat.active:
            break
        cur = ctx.current()
        ctx.scope(cur)
        char = gs.characters[cur]
        if char.is_player:
            target = next((c for c in gs.combat.turn_order
                           if c.startswith("wolf") and gs.characters[c].hp > 0), None)
            if target:
                if cur == "zara":
                    ctx.call("cast_spell", {"caster_id": "zara", "spell_name": "Fire Bolt",
                                            "target_ids": [target]}, expect=True)
                else:
                    ctx.call("attack", {"attacker_id": cur, "target_id": target,
                                        "weapon_name": "Longsword"}, expect=True)
                # Second attack in the same turn: action already consumed
                ctx.call("attack", {"attacker_id": cur, "target_id": target,
                                    "weapon_name": "Longsword"}, expect=False,
                         note="action economy: one action per turn")
        else:
            # Monster turn: statblock action by name (no Weapon entry needed)
            ctx.call("get_monster_actions", {"monster_id": cur}, expect=True)
            pc = "aldric" if gs.characters["aldric"].hp > 0 else "zara"
            ctx.call("attack", {"attacker_id": cur, "target_id": pc,
                                "weapon_name": "Bite"}, expect=True)
            # Off-turn reactions during the monster's turn:
            if not oa_done:
                ctx.call("opportunity_attack", {"attacker_id": "aldric", "target_id": cur,
                                                "weapon_name": "Longsword"}, expect=True)
                ctx.call("opportunity_attack", {"attacker_id": "aldric", "target_id": cur,
                                                "weapon_name": "Longsword"}, expect=False,
                         note="one reaction per round")
                oa_done = True
            if not shield_cast and gs.characters["zara"].hp > 0:
                ctx.call("cast_spell", {"caster_id": "zara", "spell_name": "Shield",
                                        "target_ids": []}, expect=True,
                         note="reaction spell off-turn")
                ctx.check("shielded" in gs.characters["zara"].conditions,
                          "Shield did not apply the shielded condition")
                shield_cast = True
        ctx.call("end_turn", {}, expect=True)
        # Turn-scope: this render's turn is over — no further acting/passing
        ctx.call("end_turn", {}, expect=False, note="fast-forward rejection")
        nxt = ctx.current()
        if nxt != cur and gs.combat.active:
            ctx.call("attack", {"attacker_id": nxt, "target_id": "aldric"
                                if nxt.startswith("wolf") else "wolf_1",
                                "weapon_name": "Bite" if nxt.startswith("wolf")
                                else "Longsword"}, expect=False,
                     note="acting for the next combatant in the same render")

    # Dying flow: put zara at 0, walk her death saves on her turn
    if gs.combat.active:
        zara = gs.characters["zara"]
        if zara.hp > 0:
            ctx.scope(None)
            ctx.call("apply_damage", {"target_id": "zara", "amount": zara.hp + 5,
                                      "damage_type": "bludgeoning"}, expect=None)
        ctx.check("unconscious" in zara.conditions or "dead" in zara.conditions,
                  "0 HP PC neither unconscious nor dead")
        if "unconscious" in zara.conditions:
            # Death saves happen on the dying PC's own turn — advance to it
            ctx.scope(None)
            for _ in range(len(gs.combat.turn_order)):
                if ctx.current() == "zara" or not gs.combat.active:
                    break
                ctx.call("end_turn", {}, expect=True)
            ctx.check(ctx.current() == "zara", "unconscious PC never got a turn")
            ctx.scope("zara")
            ctx.call("death_save", {"character_id": "zara"}, expect=True)
            ctx.call("apply_healing", {"target_id": "zara", "amount": 8}, expect=True,
                     note="healing revives the dying")
            ctx.check(zara.hp > 0 and "unconscious" not in zara.conditions,
                      "healing did not revive the dying PC")
            ctx.check(zara.death_saves.successes == 0 and zara.death_saves.failures == 0,
                      "death saves not reset after revival")

    # Clean up
    ctx.scope(None)
    if gs.combat.active:
        ctx.call("end_combat", {"xp_awarded": 100}, expect=True)
    ctx.check(not gs.combat.active, "combat still active after end_combat")
    ctx.check(not any(c.startswith("wolf") for c in gs.characters),
              "monsters not removed after end_combat")
    ctx.call("end_combat", {"xp_awarded": 100}, expect=False, note="double end_combat")


@dataclass
class EngineScenario:
    name: str
    description: str
    script: Callable[[EngineCtx], None]
    seed: int = 42


ENGINE_SCENARIOS: dict[str, EngineScenario] = {
    "engine_guards": EngineScenario(
        name="engine_guards",
        description="Free (no LLM): every dispatcher/engine guard must reject bad input.",
        script=_guard_fuzz,
    ),
    "engine_dice": EngineScenario(
        name="engine_dice",
        description="Free (no LLM): dice parser accepts valid notation, rejects garbage.",
        script=_dice_fuzz,
    ),
    "engine_combat": EngineScenario(
        name="engine_combat",
        description="Free (no LLM): deterministic combat lifecycle under turn scope.",
        script=_combat_cycle,
    ),
}
