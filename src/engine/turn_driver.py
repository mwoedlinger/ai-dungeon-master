"""One combat turn driver, shared by every front end.

The CLI and the web server each grew their own copy of the per-turn sequence,
and they drifted: the web copy skipped downed PCs outright, so a dying
character never rolled a death save and the fight could not end. Turn logic
lives here now; the front ends only render the outcomes.

The driver performs the automatic parts itself (skipping combatants who are
out of the fight, rolling death saves) and hands back a description of what
happened or what it needs. Anything requiring a UI — prompting a player,
running the LLM for a monster — is returned as an outcome for the caller.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# A round of pure auto-advance (skips, death saves, monster turns) without a
# player acting. Guards against a front end spinning forever on a stuck turn.
DEFAULT_MAX_AUTO_TURNS = 50


@dataclass
class TurnOutcome:
    """Base for what the driver decided to do."""


@dataclass
class CombatEnded(TurnOutcome):
    """Combat is over; the caller should return to exploration mode."""


@dataclass
class AutoSkipped(TurnOutcome):
    """A combatant who is out of the fight had their turn passed."""
    character_id: str
    character_name: str
    reason: str


@dataclass
class DeathSaveResolved(TurnOutcome):
    """A dying PC's turn: a death save was rolled (or skipped while stable)."""
    character_id: str
    character_name: str
    result: dict = field(default_factory=dict)
    # One of: stable_skip, died, recovered, stabilized, rolled, failed
    kind: str = "rolled"
    message: str = ""


@dataclass
class AwaitPlayerInput(TurnOutcome):
    """It is a player character's turn; the caller must collect input."""
    character_id: str
    character_name: str


@dataclass
class MonsterTurn(TurnOutcome):
    """It is a monster's turn; the caller should run *prompt* through the DM
    and then call `finish_monster_turn`."""
    character_id: str
    character_name: str
    prompt: str


@dataclass
class TurnLimitReached(TurnOutcome):
    """Too many turns advanced without a player acting — bail out."""
    turns: int


def monster_turn_prompt(character_id: str, character_name: str) -> str:
    return (
        f"[DM: It is {character_name}'s turn. "
        f"Call get_monster_actions('{character_id}') first, "
        f"then resolve their actions, then call end_turn().]"
    )


class CombatTurnDriver:
    """Advances combat one step at a time.

    Call `next_turn()` repeatedly. Each call returns exactly one outcome, so a
    front end can render death saves and skips as they happen rather than
    discovering them after the fact.
    """

    def __init__(self, game_state, dispatcher, max_auto_turns: int = DEFAULT_MAX_AUTO_TURNS):
        self.game_state = game_state
        self.dispatcher = dispatcher
        self.max_auto_turns = max_auto_turns
        self._auto_turns = 0

    # -- main entry point -----------------------------------------------------

    def next_turn(self) -> TurnOutcome:
        gs = self.game_state
        combat = gs.combat

        if not combat.active:
            self._auto_turns = 0
            return CombatEnded()

        if self._auto_turns >= self.max_auto_turns:
            logger.error(
                "Combat advanced %d turns with no player action — aborting to "
                "avoid an unbounded loop.", self._auto_turns,
            )
            self._auto_turns = 0
            return TurnLimitReached(turns=self.max_auto_turns)

        current_id = combat.current_combatant_id
        try:
            char = gs.get_character(current_id)
        except KeyError:
            self._auto_turns += 1
            self._end_turn()
            return AutoSkipped(current_id, current_id, "combatant no longer exists")

        # Out of the fight: dead anyone, or a downed monster. A downed *PC* is
        # deliberately not skipped — they still take a turn to roll death saves,
        # which is the whole reason combat can end after a party wipe.
        if "dead" in char.conditions:
            self._auto_turns += 1
            self._end_turn()
            return AutoSkipped(current_id, char.name, "dead")
        if not char.is_player and char.hp <= 0:
            self._auto_turns += 1
            self._end_turn()
            return AutoSkipped(current_id, char.name, "defeated")

        if char.is_player and char.hp <= 0:
            self._auto_turns += 1
            return self._resolve_dying_player(current_id, char)

        if char.is_player:
            self._auto_turns = 0
            return AwaitPlayerInput(current_id, char.name)

        self._auto_turns += 1
        self.dispatcher.set_turn_scope(current_id)
        return MonsterTurn(current_id, char.name, monster_turn_prompt(current_id, char.name))

    def finish_monster_turn(self, character_id: str) -> bool:
        """Force the turn to advance if the LLM narrated but never ended it.

        Without this the same monster is prompted forever. Returns True if the
        driver had to step in.
        """
        combat = self.game_state.combat
        if combat.active and combat.current_combatant_id == character_id:
            logger.warning("LLM did not end %s's turn — forcing end_turn", character_id)
            self.dispatcher.dispatch("end_turn", {})
            return True
        return False

    def finish_player_turn(self, character_id: str) -> bool:
        """End a player's turn when they have nothing left to spend.

        A player who dodges (or otherwise uses a tool that ends their turn)
        without the LLM calling end_turn would be prompted again forever. Only
        forces the turn when action, bonus action and movement are all gone —
        a spent action alone still leaves a bonus action to use.
        """
        combat = self.game_state.combat
        if not combat.active or combat.current_combatant_id != character_id:
            return False
        c = combat.combatants.get(character_id)
        if c is None:
            return False
        if c.has_action or c.has_bonus_action or c.movement_remaining > 0:
            return False
        logger.info("%s has nothing left to spend — ending their turn", character_id)
        self.dispatcher.dispatch("end_turn", {})
        return True

    # -- internals ------------------------------------------------------------

    def _end_turn(self) -> None:
        from src.engine.combat import end_turn
        end_turn(self.game_state)

    def _resolve_dying_player(self, cid: str, char) -> DeathSaveResolved:
        """A downed PC's turn is a death save, unless they have stabilized."""
        self.dispatcher.set_turn_scope(cid)

        if "stable" in char.conditions:
            self.dispatcher.dispatch("end_turn", {})
            return DeathSaveResolved(
                cid, char.name, {}, "stable_skip",
                f"{char.name} is stable but unconscious — turn skipped.",
            )

        result = self.dispatcher.dispatch("death_save", {"character_id": cid})
        self.dispatcher.dispatch("end_turn", {})

        if not result.get("success"):
            return DeathSaveResolved(
                cid, char.name, result, "failed",
                f"Could not roll a death save for {char.name}: "
                f"{result.get('error', 'unknown error')}",
            )

        roll = result.get("roll", "?")
        if result.get("dead"):
            kind, msg = "died", (
                f"{char.name} rolls a death save: {roll} — third failure. "
                f"{char.name} has died."
            )
        elif result.get("outcome") == "miraculous_recovery":
            kind, msg = "recovered", (
                f"{char.name} rolls a natural 20 — they regain 1 HP and awaken!"
            )
        elif result.get("stabilized"):
            kind, msg = "stabilized", (
                f"{char.name} rolls a death save: {roll} — third success. They are stable."
            )
        else:
            ds = char.death_saves
            kind, msg = "rolled", (
                f"{char.name} rolls a death save: {roll} "
                f"({result.get('outcome', '')}) — {ds.successes}✓ {ds.failures}✗"
            )
        return DeathSaveResolved(cid, char.name, result, kind, msg)
