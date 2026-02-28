"""Session manager — two-player turn handling and main game loop."""
from __future__ import annotations

from enum import Enum

from src.dm.dungeon_master import DungeonMaster
from src.engine.game_state import GameState
from rich.panel import Panel

from src.interface.cli import (
    console,
    display_combat_state,
    display_dice_roll,
    display_narrative,
    display_status_bar,
)
from src.log.event_log import EventLog


class TurnMode(str, Enum):
    EXPLORATION = "exploration"
    COMBAT = "combat"


class SessionManager:
    def __init__(
        self,
        dm: DungeonMaster,
        game_state: GameState,
        event_log: EventLog,
        player_names: list[str] | None = None,
    ):
        self.dm = dm
        self.game_state = game_state
        self.event_log = event_log
        self.player_names = player_names or ["Player 1", "Player 2"]
        self.mode = TurnMode.EXPLORATION
        self._last_event_idx = 0

    def run(self) -> None:
        """Main game loop."""
        console.print("\n[bold green]═══ AI Dungeon Master ═══[/bold green]\n")
        console.print("[dim]Commands: quit · /recap[/dim]\n")

        # Opening scene
        response = self.dm.process_player_input(
            "[Session start. Set the scene: describe where the party is, "
            "the atmosphere, and any immediate situation. Greet both players by their character names.]"
        )
        self._render_turn(response)

        while True:
            try:
                if self.mode == TurnMode.COMBAT:
                    self._combat_input_loop()
                else:
                    self._exploration_input_loop()
            except KeyboardInterrupt:
                console.print("\n[dim]Use 'quit' or 'exit' to save and quit.[/dim]")
            except EOFError:
                console.print("\n[dim]Session ended.[/dim]")
                break

    def _exploration_input_loop(self) -> None:
        display_status_bar(self.game_state)
        console.print("")
        try:
            player_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            raise

        if not player_input:
            return

        if player_input.lower() in ("quit", "exit", "q"):
            response = self.dm.process_player_input("[Player requests to save and quit the session.]")
            self._render_turn(response)
            raise EOFError

        if player_input.lower() in ("/recap", "recap"):
            console.print("\n[dim]Generating session recap...[/dim]")
            recap = self.dm.generate_session_recap()
            console.print(Panel(recap, title="[bold]Session Recap[/bold]", border_style="cyan"))
            return

        response = self.dm.process_player_input(player_input)
        self._render_turn(response)

        # Check if combat started
        if self.game_state.combat.active:
            self.mode = TurnMode.COMBAT

    def _combat_input_loop(self) -> None:
        combat = self.game_state.combat

        if not combat.active:
            self.mode = TurnMode.EXPLORATION
            return

        display_combat_state(self.game_state)
        console.print("")

        current_id = combat.current_combatant_id
        try:
            current_char = self.game_state.get_character(current_id)
        except KeyError:
            # Turn order has a stale ID; advance
            self.dm.process_player_input("[end_turn — stale combatant]")
            return

        if current_char.is_player:
            prompt = f"[{current_char.name}'s turn] > "
            try:
                player_input = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                raise
            if not player_input:
                return
            if player_input.lower() in ("quit", "exit", "q"):
                raise EOFError
            response = self.dm.process_player_input(
                f"[{current_char.name}]: {player_input}"
            )
        else:
            # Monster turn — DM acts automatically
            response = self.dm.process_player_input(
                f"[DM: It is {current_char.name}'s turn. "
                f"Call get_monster_actions('{current_id}') first, "
                f"then resolve their actions, then call end_turn().]"
            )

        self._render_turn(response)

        if not self.game_state.combat.active:
            self.mode = TurnMode.EXPLORATION

    def _render_turn(self, narrative: str) -> None:
        """Render new event log entries then the narrative."""
        # Render dice callout boxes for new events
        new_events = self.event_log.entries[self._last_event_idx:]
        self._last_event_idx = len(self.event_log.entries)
        for entry in new_events:
            display_dice_roll(entry)

        # Get current location name for panel header
        loc_id = self.game_state.world.current_location_id
        loc = self.game_state.world.locations.get(loc_id)
        loc_name = loc.name if loc else ""

        if narrative:
            display_narrative(narrative, location_name=loc_name)
