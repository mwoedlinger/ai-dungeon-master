"""Per-turn state snapshots, so a turn can be undone.

The player has no undo today: the DM misreads an intent, rolls dice, and the
fiction is committed. A coding harness gets this for free from version control;
here the equivalent is a deep copy of GameState taken before each player turn.

Two things are load-bearing:

* ``campaign`` is never copied. It holds an LRU cache of lazily disk-loaded
  entities, so deep-copying it is both expensive and wrong — two copies would
  desync, and touching ``.locations`` in directory mode reads every location
  from disk.
* Restore mutates the existing GameState in place. DungeonMaster,
  ContextManager, ToolDispatcher, EventLog, SessionManager and GameSession all
  hold direct references to it; rebinding a name would strand five of them.
"""
from __future__ import annotations

import copy
import logging
from collections import deque

logger = logging.getLogger(__name__)

# Fields that make up a restorable turn. `campaign` is deliberately absent.
_RESTORE_FIELDS = (
    "player_character_ids",
    "characters",
    "world",
    "combat",
    "journal",
    "conversation_history",
)

DEFAULT_MAX_DEPTH = 5


def snapshot_state(gs):
    """Deep-copy *gs*, aliasing its campaign rather than copying it."""
    campaign = gs.campaign
    gs.campaign = None
    try:
        clone = copy.deepcopy(gs)
    finally:
        gs.campaign = campaign
    clone.campaign = campaign  # shared immutable reference data
    return clone


def restore_state(target, snap) -> None:
    """Copy *snap* back onto *target*, in place.

    Deep-copies on the way in as well, so one snapshot can be restored more
    than once without later mutations leaking back into it.
    """
    for field in _RESTORE_FIELDS:
        setattr(target, field, copy.deepcopy(getattr(snap, field)))
    # campaign deliberately untouched


class SnapshotStack:
    """A bounded undo stack of game states."""

    def __init__(self, game_state, max_depth: int = DEFAULT_MAX_DEPTH):
        self._gs = game_state
        self._stack: deque = deque(maxlen=max_depth)

    def push(self, label: str) -> None:
        self._stack.append((label, snapshot_state(self._gs)))
        logger.debug("Snapshot pushed: %s (depth %d)", label, len(self._stack))

    def pop_and_restore(self) -> str | None:
        """Undo the most recent turn. Returns its label, or None if empty."""
        if not self._stack:
            return None
        label, snap = self._stack.pop()
        restore_state(self._gs, snap)
        logger.info("Restored state from before: %s", label)
        return label

    def clear(self) -> None:
        self._stack.clear()

    def __len__(self) -> int:
        return len(self._stack)
