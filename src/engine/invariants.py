"""Deterministic state linter.

The engine is the rules arbiter, but nothing checks that the state it produces
is internally coherent. This module is that check: a zero-token, zero-API pass
over `GameState` that answers "could this state exist in a legal game?".

It is the harness equivalent of a type checker — cheap enough to run after
every turn, and it catches the class of bug where two subsystems disagree
(HP above max, a dead combatant still in the turn order, spell slots below
zero) rather than requiring a bespoke test per defect.

Deliberately imports nothing from `src.dm`, so the debug harness and the
engine-only test path can use it without constructing an LLM backend.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.game_state import GameState

logger = logging.getLogger(__name__)

ERROR = "error"
WARN = "warn"

# Death saves cap at 3 successes, but a natural 1 adds *two* failures, so a
# character can legitimately sit at 4. See combat.death_save.
_MAX_SUCCESSES = 3
_MAX_FAILURES = 4

# Conditions are free-form strings by design (exhaustion_1..6, plus whatever
# apply_condition is handed). Only these three carry mechanical meaning here;
# there is deliberately no vocabulary check.
_DEAD = "dead"
_UNCONSCIOUS = "unconscious"
_STABLE = "stable"


@dataclass(frozen=True)
class Violation:
    code: str       # stable machine id, e.g. "HP_ABOVE_MAX"
    severity: str   # ERROR | WARN
    subject: str    # character id, or "combat" / "world"
    detail: str     # includes the actual numbers
    fix_hint: str = ""

    def __str__(self) -> str:
        return f"{self.code} [{self.subject}] {self.detail}"


# Violations severe enough to tell the model about. Everything else is for
# the logs: it indicates an engine bug, and the model cannot help.
SEVERE_CODES = frozenset({
    "HP_ABOVE_MAX", "HP_NEGATIVE", "SLOTS_ABOVE_MAX", "SLOTS_NEGATIVE",
    "GOLD_NEGATIVE", "DEAD_AND_ALIVE", "CONSCIOUS_AT_ZERO_HP",
    "UNCONSCIOUS_WITH_HP", "TURN_INDEX_OUT_OF_RANGE", "DOWNED_MONSTER_IS_CURRENT",
})


def check_invariants(gs: "GameState") -> list[Violation]:
    """Return every invariant violation in *gs*, most severe first."""
    out: list[Violation] = []
    out.extend(_check_characters(gs))
    out.extend(_check_combat(gs))
    out.extend(_check_world(gs))
    out.sort(key=lambda v: (v.severity != ERROR, v.code))
    return out


# --- characters ---------------------------------------------------------------

def _check_characters(gs: "GameState") -> list[Violation]:
    out: list[Violation] = []
    for cid, char in gs.characters.items():
        conds = set(char.conditions)

        if char.hp > char.max_hp:
            out.append(Violation(
                "HP_ABOVE_MAX", ERROR, cid,
                f"hp={char.hp} exceeds max_hp={char.max_hp}",
                "Clamp to max_hp; healing should never overshoot.",
            ))
        if char.hp < 0:
            out.append(Violation(
                "HP_NEGATIVE", ERROR, cid, f"hp={char.hp}",
                "Damage should floor at 0, not go negative.",
            ))
        if char.temp_hp < 0:
            out.append(Violation("TEMP_HP_NEGATIVE", ERROR, cid, f"temp_hp={char.temp_hp}"))
        if char.gold < 0:
            out.append(Violation(
                "GOLD_NEGATIVE", ERROR, cid, f"gold={char.gold}",
                "A purchase was allowed that the character could not afford.",
            ))

        for level, remaining in char.spell_slots.items():
            maximum = char.max_spell_slots.get(level, 0)
            if remaining > maximum:
                out.append(Violation(
                    "SLOTS_ABOVE_MAX", ERROR, cid,
                    f"level {level}: {remaining}/{maximum} remaining",
                ))
            if remaining < 0:
                out.append(Violation(
                    "SLOTS_NEGATIVE", ERROR, cid, f"level {level}: {remaining}",
                    "A spell was cast without checking slot availability.",
                ))

        for item in char.inventory:
            if item.quantity <= 0:
                out.append(Violation(
                    "ITEM_QTY_NONPOSITIVE", ERROR, cid,
                    f"{item.name!r} quantity={item.quantity}",
                    "Items at zero quantity should be removed, not kept.",
                ))

        if char.is_player and len(char.attuned_items) > 3:
            out.append(Violation(
                "ATTUNEMENT_OVER_LIMIT", ERROR, cid,
                f"{len(char.attuned_items)} attuned items (limit 3)",
            ))

        out.extend(_check_life_state(cid, char, conds))
        out.extend(_check_death_saves(cid, char, conds))

        if char.concentration and (_UNCONSCIOUS in conds or _DEAD in conds):
            out.append(Violation(
                "CONCENTRATION_ON_UNCONSCIOUS", WARN, cid,
                f"concentrating on {char.concentration!r} while {sorted(conds)}",
                "Concentration breaks when a character drops.",
            ))
    return out


def _check_life_state(cid: str, char, conds: set[str]) -> list[Violation]:
    """The dead/unconscious/stable triangle.

    Legal terminal states, none of which may be reported:
      - hp=0, unconscious, stable        (three death-save successes, per RAW)
      - hp=0, dead
      - hp=0 on a monster before end_combat cleans it up
    """
    out: list[Violation] = []
    if _DEAD in conds and char.hp > 0:
        out.append(Violation(
            "DEAD_AND_ALIVE", ERROR, cid,
            f"marked dead with hp={char.hp}",
            "Revival must remove the 'dead' condition.",
        ))
    if _DEAD in conds and _STABLE in conds:
        out.append(Violation(
            "DEAD_AND_STABLE", ERROR, cid, "both 'dead' and 'stable'",
        ))
    if char.hp <= 0 and char.is_player and not (conds & {_UNCONSCIOUS, _DEAD}):
        # Monsters are exempt: they sit at 0 HP in the turn order until
        # end_combat removes them.
        out.append(Violation(
            "CONSCIOUS_AT_ZERO_HP", ERROR, cid,
            f"hp={char.hp} but neither unconscious nor dead",
            "A PC reduced to 0 HP must be marked unconscious so death saves run.",
        ))
    if char.hp > 0 and _UNCONSCIOUS in conds:
        out.append(Violation(
            "UNCONSCIOUS_WITH_HP", ERROR, cid,
            f"hp={char.hp} while unconscious",
            "Healing above 0 must clear 'unconscious'.",
        ))
    return out


def _check_death_saves(cid: str, char, conds: set[str]) -> list[Violation]:
    out: list[Violation] = []
    ds = char.death_saves
    if not (0 <= ds.successes <= _MAX_SUCCESSES) or not (0 <= ds.failures <= _MAX_FAILURES):
        out.append(Violation(
            "DEATH_SAVE_COUNT_IMPOSSIBLE", ERROR, cid,
            f"successes={ds.successes} failures={ds.failures}",
        ))
    if char.hp > 0 and (ds.successes or ds.failures) and _UNCONSCIOUS not in conds:
        out.append(Violation(
            "DEATH_SAVES_STALE", WARN, cid,
            f"conscious at hp={char.hp} with saves {ds.successes}/{ds.failures}",
            "Death saves should reset once a character is back up.",
        ))
    return out


# --- combat -------------------------------------------------------------------

def _check_combat(gs: "GameState") -> list[Violation]:
    combat = gs.combat
    out: list[Violation] = []

    if not combat.active:
        for cid, char in gs.characters.items():
            if not char.is_player and cid not in gs.player_character_ids:
                if char.hp <= 0:
                    out.append(Violation(
                        "MONSTER_LINGERING_AFTER_COMBAT", WARN, cid,
                        "downed monster still present after combat ended",
                        "end_combat should remove defeated monsters.",
                    ))
        return out

    if not combat.turn_order:
        out.append(Violation(
            "COMBAT_ACTIVE_EMPTY_ORDER", ERROR, "combat",
            "combat is active with an empty turn order",
        ))
        return out

    # Computed against len(turn_order) directly: CombatState.current_combatant_id
    # does not bounds-check and would raise IndexError here.
    if not 0 <= combat.current_turn_index < len(combat.turn_order):
        out.append(Violation(
            "TURN_INDEX_OUT_OF_RANGE", ERROR, "combat",
            f"current_turn_index={combat.current_turn_index} "
            f"but turn_order has {len(combat.turn_order)} entries",
            "end_turn must wrap the index when the round rolls over.",
        ))

    if combat.round < 1:
        out.append(Violation(
            "ROUND_NOT_POSITIVE", ERROR, "combat", f"round={combat.round} while active",
        ))

    for cid in combat.turn_order:
        if cid not in gs.characters:
            out.append(Violation(
                "TURN_ORDER_MISSING_CHARACTER", ERROR, cid,
                "in turn_order but absent from game_state.characters",
            ))

    if len(combat.turn_order) != len(set(combat.turn_order)):
        seen: set[str] = set()
        dupes = sorted({cid for cid in combat.turn_order if cid in seen or seen.add(cid)})
        out.append(Violation(
            "TURN_ORDER_DUPLICATES", ERROR, "combat",
            f"duplicate entries in turn order: {dupes}",
        ))

    current = combat.turn_order[combat.current_turn_index] \
        if 0 <= combat.current_turn_index < len(combat.turn_order) else None
    if current is not None:
        char = gs.characters.get(current)
        # A downed monster may sit in the turn order, but it must never be the
        # combatant whose turn it is — that means the skip logic failed.
        if char is not None and not char.is_player and char.hp <= 0:
            out.append(Violation(
                "DOWNED_MONSTER_IS_CURRENT", ERROR, current,
                "a defeated monster is the current combatant",
                "end_turn should skip combatants that are out of the fight.",
            ))

    if set(combat.combatants) != set(combat.turn_order):
        only_order = set(combat.turn_order) - set(combat.combatants)
        only_combatants = set(combat.combatants) - set(combat.turn_order)
        out.append(Violation(
            "COMBATANT_SET_MISMATCH", ERROR, "combat",
            f"turn_order-only={sorted(only_order)} combatants-only={sorted(only_combatants)}",
        ))

    out.extend(_check_condition_drift(gs))
    return out


def _check_condition_drift(gs: "GameState") -> list[Violation]:
    """Durations live on Combatant, names on Character. They can drift.

    Only one direction is a defect: a duration with no matching condition name
    is an orphan. The reverse is legal — a condition applied outside combat, or
    an indefinite one, has no duration entry.
    """
    out: list[Violation] = []
    for cid, combatant in gs.combat.combatants.items():
        char = gs.characters.get(cid)
        if char is None:
            continue
        orphans = set(combatant.condition_durations) - set(char.conditions)
        if orphans:
            out.append(Violation(
                "CONDITION_DURATION_DRIFT", WARN, cid,
                f"durations tracked for conditions the character lacks: {sorted(orphans)}",
                "Removing a condition should drop its duration entry.",
            ))
    return out


# --- world --------------------------------------------------------------------

def _check_world(gs: "GameState") -> list[Violation]:
    out: list[Violation] = []
    t = gs.world.time
    if not 0 <= t.hour < 24:
        out.append(Violation("CLOCK_HOUR_OUT_OF_RANGE", ERROR, "world", f"hour={t.hour}"))
    if not 0 <= t.minute < 60:
        out.append(Violation("CLOCK_MINUTE_OUT_OF_RANGE", ERROR, "world", f"minute={t.minute}"))
    if t.day < 1:
        out.append(Violation("CLOCK_DAY_NOT_POSITIVE", ERROR, "world", f"day={t.day}"))
    if gs.world.current_location_id not in gs.world.locations:
        out.append(Violation(
            "CURRENT_LOCATION_UNKNOWN", ERROR, "world",
            f"current_location_id={gs.world.current_location_id!r} not in world.locations",
        ))
    return out


# --- repair -------------------------------------------------------------------

def repair_invariants(gs: "GameState") -> list[Violation]:
    """Fix the unambiguously-repairable violations, returning what was fixed.

    Deliberately conservative: nothing here touches the dead/unconscious/stable
    conditions or the turn order, because the correct repair there depends on
    how the state broke. Shipped and tested but not yet wired into the loop.
    """
    fixed: list[Violation] = []
    for cid, char in gs.characters.items():
        if char.hp > char.max_hp:
            fixed.append(Violation("HP_ABOVE_MAX", ERROR, cid, f"clamped {char.hp} -> {char.max_hp}"))
            char.hp = char.max_hp
        if char.hp < 0:
            fixed.append(Violation("HP_NEGATIVE", ERROR, cid, f"clamped {char.hp} -> 0"))
            char.hp = 0
        if char.temp_hp < 0:
            fixed.append(Violation("TEMP_HP_NEGATIVE", ERROR, cid, f"clamped {char.temp_hp} -> 0"))
            char.temp_hp = 0
        if char.gold < 0:
            fixed.append(Violation("GOLD_NEGATIVE", ERROR, cid, f"clamped {char.gold} -> 0"))
            char.gold = 0
        for level, remaining in list(char.spell_slots.items()):
            maximum = char.max_spell_slots.get(level, 0)
            if remaining > maximum:
                fixed.append(Violation("SLOTS_ABOVE_MAX", ERROR, cid, f"L{level} {remaining} -> {maximum}"))
                char.spell_slots[level] = maximum
            elif remaining < 0:
                fixed.append(Violation("SLOTS_NEGATIVE", ERROR, cid, f"L{level} {remaining} -> 0"))
                char.spell_slots[level] = 0
        empties = [i for i in char.inventory if i.quantity <= 0]
        for item in empties:
            fixed.append(Violation("ITEM_QTY_NONPOSITIVE", ERROR, cid, f"dropped {item.name!r}"))
            char.inventory.remove(item)
        if char.hp > 0 and (char.death_saves.successes or char.death_saves.failures) \
                and _UNCONSCIOUS not in char.conditions:
            fixed.append(Violation("DEATH_SAVES_STALE", WARN, cid, "reset death saves"))
            char.death_saves.successes = 0
            char.death_saves.failures = 0

    for cid, combatant in gs.combat.combatants.items():
        char = gs.characters.get(cid)
        if char is None:
            continue
        for cond in set(combatant.condition_durations) - set(char.conditions):
            fixed.append(Violation("CONDITION_DURATION_DRIFT", WARN, cid, f"dropped orphan {cond!r}"))
            del combatant.condition_durations[cond]

    return fixed
