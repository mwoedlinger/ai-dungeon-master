"""GameSession and WebSocket handler — core of the web API."""
from __future__ import annotations

import asyncio
import json
import logging
import queue as thread_queue
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.events import EventBridge
from src.api.schemas import GameStateSnapshot
from src.dm.dungeon_master import DungeonMaster
from src.engine.game_state import GameState
from src.log.event_log import EventLog

logger = logging.getLogger(__name__)

router = APIRouter()

_SENTINEL = object()


@dataclass
class GameSession:
    """Manages a single game session for the web API."""

    dm: DungeonMaster
    game_state: GameState
    event_log: EventLog
    event_bridge: EventBridge
    save_path: str = "saves/autosave.json"
    mode: str = "exploration"
    _opening_done: bool = field(default=False, repr=False)
    _turn_driver: object = field(default=None, repr=False)

    @property
    def turn_driver(self):
        """Shared combat turn driver (lazy — needs the dispatcher)."""
        if self._turn_driver is None:
            from src.engine.turn_driver import CombatTurnDriver
            self._turn_driver = CombatTurnDriver(
                self.game_state, self.dm.tool_dispatcher,
            )
        return self._turn_driver

    def snapshot(self) -> GameStateSnapshot:
        """Build a full state snapshot for the frontend."""
        combat = self.game_state.combat
        current_turn = None
        if combat.active and combat.turn_order:
            cid = combat.current_combatant_id
            try:
                char = self.game_state.get_character(cid)
                current_turn = {
                    "character_id": cid,
                    "character_name": char.name,
                    "is_player": char.is_player,
                }
            except KeyError:
                pass

        return GameStateSnapshot(
            characters=[c.model_dump() for c in self.game_state.player_characters],
            combat=combat.model_dump() if combat.active else None,
            world=self.game_state.world.model_dump(),
            journal=self.game_state.journal.model_dump(),
            mode=self.mode,
            current_turn=current_turn,
        )

    async def handle_player_input(self, text: str, ws: WebSocket) -> None:
        """Process player input through the DM and stream results over WebSocket."""
        sync_queue: thread_queue.Queue = thread_queue.Queue()

        def on_chunk(chunk: str) -> None:
            sync_queue.put({"type": "narrative_chunk", "text": chunk})

        loc_before = self.game_state.world.current_location_id

        # Flush any pending events before starting
        for evt in self.event_bridge.drain_new_events():
            await ws.send_json(evt)

        # Run blocking DM call in thread
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(
            None, lambda: self.dm.process_player_input(text, on_text_chunk=on_chunk)
        )

        # Drain queue while DM is processing
        while True:
            try:
                msg = sync_queue.get_nowait()
            except thread_queue.Empty:
                if task.done():
                    # Drain remaining
                    while not sync_queue.empty():
                        msg = sync_queue.get_nowait()
                        for evt in self.event_bridge.drain_new_events():
                            await ws.send_json(evt)
                        await ws.send_json(msg)
                    break
                await asyncio.sleep(0.01)
                continue

            # Flush mechanical events before each narrative chunk
            for evt in self.event_bridge.drain_new_events():
                await ws.send_json(evt)
            await ws.send_json(msg)

        # Flush any remaining events
        for evt in self.event_bridge.drain_new_events():
            await ws.send_json(evt)

        # Wait for the task result (should already be done)
        await task

        await ws.send_json({"type": "narrative_end"})

        # Location change detection
        loc_after = self.game_state.world.current_location_id
        if loc_after != loc_before:
            loc = self.game_state.world.locations.get(loc_after)
            await ws.send_json({
                "type": "location_change",
                "location": {"id": loc_after, "name": loc.name if loc else loc_after},
            })

        # Mode change detection
        combat_active = self.game_state.combat.active
        old_mode = self.mode
        self.mode = "combat" if combat_active else "exploration"
        if self.mode != old_mode:
            await ws.send_json({"type": "mode_change", "mode": self.mode})

        # Push full state update
        await ws.send_json({
            "type": "state_update",
            "payload": self.snapshot().model_dump(),
        })

    async def handle_command(self, name: str, args: str, ws: WebSocket) -> dict[str, Any]:
        """Handle a slash command. Returns a result dict."""
        if name == "save":
            self.game_state.save(self.save_path)
            return {"status": "ok", "message": f"Game saved to {self.save_path}"}
        elif name == "quit":
            self.game_state.save(self.save_path)
            return {"status": "quit", "message": "Game saved. Session ended."}
        elif name == "exit":
            return {"status": "quit", "message": "Session ended without saving."}
        elif name == "recap":
            recap = self.dm.generate_session_recap()
            return {"status": "ok", "recap": recap}
        else:
            return {"status": "error", "message": f"Unknown command: {name}"}

    async def run_opening_scene(self, ws: WebSocket) -> None:
        """Generate the opening scene narration."""
        if self._opening_done:
            return
        self._opening_done = True
        await self.handle_player_input(
            "[Session start. Set the scene: describe where the party is, "
            "the atmosphere, and any immediate situation. Greet both players "
            "by their character names.]",
            ws,
        )


async def _process_combat_turns(session: GameSession, ws: WebSocket) -> None:
    """Advance combat until a player must act, using the shared turn driver.

    Previously this reimplemented the turn sequence and skipped every combatant
    at 0 HP — including player characters, who therefore never rolled death
    saves and could neither die nor stabilize, leaving the fight unwinnable.
    """
    from src.engine.turn_driver import (
        AutoSkipped, AwaitPlayerInput, CombatEnded, DeathSaveResolved,
        MonsterTurn, TurnLimitReached,
    )

    driver = session.turn_driver
    combat = session.game_state.combat

    while True:
        outcome = driver.next_turn()

        if isinstance(outcome, CombatEnded):
            break

        if isinstance(outcome, TurnLimitReached):
            logger.error("Combat stalled after %d auto-advanced turns", outcome.turns)
            await ws.send_json({
                "type": "notice",
                "level": "error",
                "message": "Combat stalled and was ended by the engine.",
            })
            session.dm.tool_dispatcher.dispatch("end_combat", {"xp_awarded": 0})
            break

        if isinstance(outcome, AutoSkipped):
            continue

        if isinstance(outcome, DeathSaveResolved):
            await ws.send_json({
                "type": "death_save",
                "character_id": outcome.character_id,
                "character_name": outcome.character_name,
                "kind": outcome.kind,
                "message": outcome.message,
                "result": outcome.result,
            })
            await ws.send_json({
                "type": "state_update",
                "payload": session.snapshot().model_dump(),
            })
            continue

        if isinstance(outcome, AwaitPlayerInput):
            await ws.send_json({
                "type": "turn_prompt",
                "character_id": outcome.character_id,
                "character_name": outcome.character_name,
                "is_player": True,
            })
            break

        assert isinstance(outcome, MonsterTurn)
        await ws.send_json({
            "type": "turn_prompt",
            "character_id": outcome.character_id,
            "character_name": outcome.character_name,
            "is_player": False,
        })
        await session.handle_player_input(outcome.prompt, ws)
        driver.finish_monster_turn(outcome.character_id)

    # If combat just ended
    if not combat.active and session.mode == "combat":
        session.mode = "exploration"
        await ws.send_json({"type": "mode_change", "mode": "exploration"})
        await ws.send_json({
            "type": "state_update",
            "payload": session.snapshot().model_dump(),
        })


@router.websocket("/ws")
async def websocket_handler(ws: WebSocket) -> None:
    """Main WebSocket endpoint for gameplay."""
    await ws.accept()
    session: GameSession | None = ws.app.state.session  # type: ignore[attr-defined]

    if session is None:
        await ws.send_json({"type": "error", "message": "No active session. POST /api/session/new first."})
        await ws.close()
        return

    # Send initial state
    await ws.send_json({
        "type": "state_update",
        "payload": session.snapshot().model_dump(),
    })

    # Run opening scene if this is a fresh session
    if not session._opening_done:
        await session.run_opening_scene(ws)

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "player_input":
                text = data.get("text", "").strip()
                if not text:
                    continue

                # In combat, prefix with character name and restrict the
                # render to that combatant's turn — without the scope the LLM
                # can end other combatants' turns and fast-forward whole rounds.
                turn_scope = ""
                if session.mode == "combat" and session.game_state.combat.active:
                    combat = session.game_state.combat
                    try:
                        current_char = session.game_state.get_character(
                            combat.current_combatant_id
                        )
                        if current_char.is_player:
                            text = f"[{current_char.name}]: {text}"
                            turn_scope = combat.current_combatant_id
                    except KeyError:
                        pass
                    session.dm.tool_dispatcher.set_turn_scope(turn_scope)

                session.dm.snapshots.push(text[:60])
                await session.handle_player_input(text, ws)

                if turn_scope:
                    session.turn_driver.finish_player_turn(turn_scope)

                # Auto-process combat turns (monsters, dead combatants)
                if session.game_state.combat.active:
                    await _process_combat_turns(session, ws)
                elif session.mode == "combat":
                    # Combat just ended during handle_player_input
                    session.mode = "exploration"
                    await ws.send_json({"type": "mode_change", "mode": "exploration"})

            elif msg_type == "command":
                name = data.get("name", "")
                args = data.get("args", "")
                result = await session.handle_command(name, args, ws)
                await ws.send_json({"type": "command_result", **result})
                if result.get("status") == "quit":
                    await ws.close()
                    return

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        logger.exception("WebSocket handler error")
        try:
            await ws.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
