"""Session manager — two-player turn handling and main game loop."""
from __future__ import annotations

from enum import Enum

from src.dm.dungeon_master import DungeonMaster
from src.engine.game_state import GameState

from src.interface.cli import (
    NarrativeStreamer,
    clear_screen,
    console,
    display_combat_state,
    display_dice_roll,
    display_header,
    display_location_transition,
    display_narrative,
    display_status_bar,
    display_turn_separator,
    erase_lines,
    measure_combat_state_height,
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
        self._last_location_id: str | None = None
        self._combat_status_lines = 0  # lines occupied by last combat status bar

    def run(self) -> None:
        """Main game loop."""
        clear_screen()
        display_header()
        self._last_location_id = self.game_state.world.current_location_id

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

        # Legacy bare-word shortcuts — behave exactly like /quit (save + exit)
        if player_input.lower() in ("quit", "exit", "q"):
            try_handle_command("/quit", self._build_command_context())
            raise EOFError

        self._process_and_render(player_input)

        # Check if combat started
        if self.game_state.combat.active:
            self.mode = TurnMode.COMBAT

    def _erase_combat_status(self) -> None:
        """Erase the previously printed combat status bar using ANSI cursor movement."""
        if self._combat_status_lines > 0:
            erase_lines(self._combat_status_lines)
            self._combat_status_lines = 0

    def _show_combat_status(self) -> None:
        """Print the combat status bar and track its height for later erasure."""
        self._combat_status_lines = measure_combat_state_height(self.game_state)
        display_combat_state(self.game_state)

    def _combat_input_loop(self) -> None:
        combat = self.game_state.combat

        if not combat.active:
            self.mode = TurnMode.EXPLORATION
            return

        # Auto-skip dead/missing combatants without involving the LLM
        current_id = combat.current_combatant_id
        try:
            current_char = self.game_state.get_character(current_id)
        except KeyError:
            from src.engine.combat import end_turn
            end_turn(self.game_state)
            return
        if "dead" in current_char.conditions or (
            not current_char.is_player and current_char.hp <= 0
        ):
            from src.engine.combat import end_turn
            end_turn(self.game_state)
            return

        # Unconscious PC: their turn is a death save (auto-rolled), unless stable
        if current_char.is_player and current_char.hp <= 0:
            self._handle_dying_player_turn(current_id, current_char)
            if not self.game_state.combat.active:
                self.mode = TurnMode.EXPLORATION
            return

        self._show_combat_status()
        console.print("")
        self._combat_status_lines += 1  # account for the blank line

        if current_char.is_player:
            prompt = f"[{current_char.name}'s turn] > "
            try:
                player_input = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                raise
            if not player_input:
                self._erase_combat_status()
                return
            # Slash commands work in combat too
            if player_input.startswith("/"):
                ctx = self._build_command_context()
                try_handle_command(player_input, ctx)
                if ctx.should_exit:
                    raise EOFError
                self._erase_combat_status()
                return
            if player_input.lower() in ("quit", "exit", "q"):
                try_handle_command("/quit", self._build_command_context())
                raise EOFError

            # Erase status bar + input line, then show turn content
            self._combat_status_lines += 1  # the input line
            self._erase_combat_status()
            display_turn_separator(current_char.name, is_player=True)
            self._process_and_render(
                f"[{current_char.name}]: {player_input}",
                combat=True, turn_scope=current_id,
            )
        else:
            # Monster turn — DM acts automatically; erase status bar first
            self._erase_combat_status()
            display_turn_separator(current_char.name, is_player=False)
            self._process_and_render(
                f"[DM: It is {current_char.name}'s turn. "
                f"Call get_monster_actions('{current_id}') first, "
                f"then resolve their actions, then call end_turn().]",
                combat=True, turn_scope=current_id,
            )
            # If the LLM narrated but never called end_turn, the same monster
            # would be prompted again forever — force the turn to advance.
            combat = self.game_state.combat
            if combat.active and combat.current_combatant_id == current_id:
                console.print(f"[dim]{current_char.name}'s turn ends.[/dim]")
                self.dm.tool_dispatcher.dispatch("end_turn", {})

        if not self.game_state.combat.active:
            self.mode = TurnMode.EXPLORATION

    def _handle_dying_player_turn(self, current_id: str, current_char) -> None:
        """Roll a death save for an unconscious PC (or skip if stable), then end the turn."""
        self.dm.tool_dispatcher.set_turn_scope(current_id)
        dispatch = self.dm.tool_dispatcher.dispatch
        if "stable" in current_char.conditions:
            console.print(f"[dim]{current_char.name} is stable but unconscious — turn skipped.[/dim]")
        else:
            result = dispatch("death_save", {"character_id": current_id})
            if result.get("success"):
                roll = result.get("roll", "?")
                outcome = result.get("outcome", "")
                if result.get("dead"):
                    console.print(f"[bold red]{current_char.name} rolls a death save: {roll} — "
                                  f"third failure. {current_char.name} has died.[/bold red]")
                elif outcome == "miraculous_recovery":
                    console.print(f"[bold green]{current_char.name} rolls a natural 20 — "
                                  f"they regain 1 HP and awaken![/bold green]")
                elif result.get("stabilized"):
                    console.print(f"[green]{current_char.name} rolls a death save: {roll} — "
                                  f"third success. They are stable.[/green]")
                else:
                    succ = current_char.death_saves.successes
                    fail = current_char.death_saves.failures
                    console.print(f"[yellow]{current_char.name} rolls a death save: {roll} "
                                  f"({outcome}) — {succ}✓ {fail}✗[/yellow]")
        dispatch("end_turn", {})

    def _process_and_render(
        self, player_input: str, *, combat: bool = False,
        turn_scope: str = "",
    ) -> None:
        """Process input with streaming output, then show dice rolls and narrative.

        *turn_scope* restricts which combatant this render may resolve:
        the current combatant's id during combat turns, "" otherwise (so a
        combat started mid-render locks until the first turn is prompted).
        """
        self.dm.tool_dispatcher.set_turn_scope(turn_scope)
        loc_before = self.game_state.world.current_location_id
        loc = self.game_state.world.locations.get(loc_before)
        loc_name = loc.name if loc else ""

        # Show dice rolls that happened before streaming starts
        self._flush_dice_rolls()

        # Set up the narrative streamer
        streamer = NarrativeStreamer(location_name=loc_name, combat=combat)
        streamed_any = False

        def on_chunk(text: str) -> None:
            nonlocal streamed_any
            if not streamed_any:
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
                display_narrative(response, location_name=loc_name, combat=combat)

        # Rolls logged after streaming began would otherwise surface under the
        # NEXT render's turn separator — flush them here, where they belong.
        self._flush_dice_rolls()

        # Check for location transition
        loc_after = self.game_state.world.current_location_id
        if loc_after != loc_before:
            new_loc = self.game_state.world.locations.get(loc_after)
            if new_loc:
                display_location_transition(new_loc.name)
            self._last_location_id = loc_after

    def _flush_dice_rolls(self) -> None:
        """Render any new dice roll events from the event log."""
        new_events = self.event_log.entries[self._last_event_idx:]
        self._last_event_idx = len(self.event_log.entries)
        for entry in new_events:
            display_dice_roll(entry)
