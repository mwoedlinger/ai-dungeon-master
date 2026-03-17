"""Session manager — two-player turn handling and main game loop."""
from __future__ import annotations

from enum import Enum

from src.dm.dungeon_master import DungeonMaster
from src.engine.game_state import GameState
from rich.panel import Panel

from src.interface.cli import (
    NarrativeStreamer,
    clear_screen,
    console,
    display_combat_state,
    display_dice_roll,
    display_header,
    display_narrative,
    display_status_bar,
)
from src.interface.commands import CommandContext, try_handle_command
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
        save_path: str = "saves/autosave.json",
    ):
        self.dm = dm
        self.game_state = game_state
        self.event_log = event_log
        self.player_names = player_names or ["Player 1", "Player 2"]
        self.save_path = save_path
        self.mode = TurnMode.EXPLORATION
        self._last_event_idx = 0

    def run(self) -> None:
        """Main game loop."""
        clear_screen()
        display_header()

        # Opening scene
        self._process_and_render(
            "[Session start. Set the scene: describe where the party is, "
            "the atmosphere, and any immediate situation. Greet both players by their character names.]"
        )

        while True:
            try:
                if self.mode == TurnMode.COMBAT:
                    self._combat_input_loop()
                else:
                    self._exploration_input_loop()
            except KeyboardInterrupt:
                console.print("\n[dim]Use /quit to save and quit, or /exit to quit without saving.[/dim]")
            except EOFError:
                console.print("\n[dim]Session ended.[/dim]")
                break

    def _build_command_context(self) -> CommandContext:
        return CommandContext(
            game_state=self.game_state,
            dm=self.dm,
            save_path=self.save_path,
        )

    def _exploration_input_loop(self) -> None:
        display_status_bar(self.game_state)
        console.print("")
        try:
            player_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            raise

        if not player_input:
            return

        # Handle slash commands
        if player_input.startswith("/"):
            ctx = self._build_command_context()
            try_handle_command(player_input, ctx)
            if ctx.should_exit:
                raise EOFError
            return

        # Legacy bare-word shortcuts for backward compat
        if player_input.lower() in ("quit", "exit", "q"):
            self._process_and_render("[Player requests to save and quit the session.]")
            raise EOFError

        # Clear screen and redraw for new turn
        clear_screen()
        display_header()
        self._process_and_render(player_input)

        # Check if combat started
        if self.game_state.combat.active:
            self.mode = TurnMode.COMBAT

    def _combat_input_loop(self) -> None:
        combat = self.game_state.combat

        if not combat.active:
            self.mode = TurnMode.EXPLORATION
            return

        # Auto-skip dead combatants without involving the LLM
        current_id = combat.current_combatant_id
        try:
            current_char = self.game_state.get_character(current_id)
        except KeyError:
            from src.engine.combat import end_turn
            end_turn(self.game_state)
            return
        if current_char.hp <= 0 or "dead" in current_char.conditions:
            from src.engine.combat import end_turn
            end_turn(self.game_state)
            return

        display_combat_state(self.game_state)
        console.print("")

        if current_char.is_player:
            prompt = f"[{current_char.name}'s turn] > "
            try:
                player_input = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                raise
            if not player_input:
                return
            # Slash commands work in combat too
            if player_input.startswith("/"):
                ctx = self._build_command_context()
                try_handle_command(player_input, ctx)
                if ctx.should_exit:
                    raise EOFError
                return
            if player_input.lower() in ("quit", "exit", "q"):
                raise EOFError

            clear_screen()
            display_header()
            display_combat_state(self.game_state)
            self._display_turn_header(current_char.name, is_player=True)
            self._process_and_render(f"[{current_char.name}]: {player_input}")
        else:
            # Monster turn — DM acts automatically
            clear_screen()
            display_header()
            display_combat_state(self.game_state)
            self._display_turn_header(current_char.name, is_player=False)
            self._process_and_render(
                f"[DM: It is {current_char.name}'s turn. "
                f"Call get_monster_actions('{current_id}') first, "
                f"then resolve their actions, then call end_turn().]"
            )

        if not self.game_state.combat.active:
            self.mode = TurnMode.EXPLORATION

    @staticmethod
    def _display_turn_header(name: str, *, is_player: bool) -> None:
        """Print a clear visual separator for the current combatant's turn."""
        if is_player:
            console.print(f"\n  [bold cyan]── {name}'s Turn ──[/bold cyan]\n")
        else:
            console.print(f"\n  [bold red]── {name}'s Turn ──[/bold red]\n")

    def _process_and_render(self, player_input: str) -> None:
        """Process input with streaming output, then show dice rolls and narrative."""
        # Get location name for the streamer header
        loc_id = self.game_state.world.current_location_id
        loc = self.game_state.world.locations.get(loc_id)
        loc_name = loc.name if loc else ""

        # Show dice rolls that happened before streaming starts
        self._flush_dice_rolls()

        # Set up the narrative streamer
        streamer = NarrativeStreamer(location_name=loc_name)
        streamed_any = False

        def on_chunk(text: str) -> None:
            nonlocal streamed_any
            if not streamed_any:
                # Flush any dice rolls that accumulated during tool calls
                self._flush_dice_rolls()
                streamed_any = True
            streamer.write_chunk(text)

        # Process through the DM with streaming
        response = self.dm.process_player_input(player_input, on_text_chunk=on_chunk)

        if streamed_any:
            streamer.end()
        else:
            # Fallback: no streaming happened (e.g. non-streaming backend)
            self._flush_dice_rolls()
            if response:
                display_narrative(response, location_name=loc_name)

    def _flush_dice_rolls(self) -> None:
        """Render any new dice roll events from the event log."""
        new_events = self.event_log.entries[self._last_event_idx:]
        self._last_event_idx = len(self.event_log.entries)
        for entry in new_events:
            display_dice_roll(entry)
