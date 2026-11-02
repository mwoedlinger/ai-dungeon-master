"""Session manager — two-player turn handling and main game loop."""
from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


class TurnMode(str, Enum):
    EXPLORATION = "exploration"
    COMBAT = "combat"


# Bare words (no slash) that open an interactive management screen.
_INVENTORY_WORDS = {"i", "inv", "inventory"}
_CHARACTER_WORDS = {"c", "char", "character"}
_SCREEN_WORDS = _INVENTORY_WORDS | _CHARACTER_WORDS


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
        self._turn_driver = None

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

    def _maybe_open_screen(self, player_input: str) -> bool:
        """Open an interactive management screen for a bare hotkey word.

        Returns True if *player_input* was a screen hotkey (and was handled).
        Falls back to the static slash-command render when there's no TTY, so the
        headless harness and piped stdin keep working unchanged.
        """
        word = player_input.lower()
        if word not in _SCREEN_WORDS:
            return False

        from src.interface.screens.menu import interactive_status

        interactive, reason = interactive_status()
        if not interactive:
            console.print(f"[dim]Interactive screen unavailable ({reason}); showing text view.[/dim]")

        if word in _INVENTORY_WORDS:
            if interactive:
                from src.interface.screens.inventory_screen import run_inventory_screen
                run_inventory_screen(self.game_state)
            else:
                try_handle_command("/inventory", self._build_command_context())
        else:  # character
            self._open_character_sheet(interactive)
        return True

    def _open_character_sheet(self, interactive: bool) -> None:
        if interactive:
            from src.interface.screens.character_screen import run_character_screen
            run_character_screen(self.game_state)
            return
        # Non-TTY fallback: print every player's static sheet.
        from src.interface.commands import _show_character_sheet
        ctx = self._build_command_context()
        for p in self.game_state.player_characters:
            _show_character_sheet(p.id, ctx)

    def _exploration_input_loop(self) -> None:
        display_status_bar(self.game_state)
        console.print("")
        try:
            player_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            raise

        if not player_input:
            return

        # Interactive management screens (bare hotkeys: i / c)
        if self._maybe_open_screen(player_input):
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

        # Snapshot after command/screen dispatch, so /retcon never snapshots
        # itself and the stack holds only real turns.
        self.dm.snapshots.push(player_input[:60])
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

    @property
    def turn_driver(self):
        """Shared combat turn driver (lazily built — needs the dispatcher)."""
        if self._turn_driver is None:
            from src.engine.turn_driver import CombatTurnDriver
            self._turn_driver = CombatTurnDriver(
                self.game_state, self.dm.tool_dispatcher,
            )
        return self._turn_driver

    def _combat_input_loop(self) -> None:
        from src.engine.turn_driver import (
            AutoSkipped, AwaitPlayerInput, CombatEnded, DeathSaveResolved,
            MonsterTurn, TurnLimitReached,
        )

        outcome = self.turn_driver.next_turn()

        if isinstance(outcome, CombatEnded):
            self.mode = TurnMode.EXPLORATION
            return

        if isinstance(outcome, TurnLimitReached):
            console.print(
                "[bold red]Combat stalled — too many turns passed without a "
                "player acting. Ending combat.[/bold red]"
            )
            self.dm.tool_dispatcher.dispatch("end_combat", {"xp_awarded": 0})
            self.mode = TurnMode.EXPLORATION
            return

        if isinstance(outcome, AutoSkipped):
            logger.debug("Skipped %s (%s)", outcome.character_name, outcome.reason)
            return

        if isinstance(outcome, DeathSaveResolved):
            self._render_death_save(outcome)
            if not self.game_state.combat.active:
                self.mode = TurnMode.EXPLORATION
            return

        if isinstance(outcome, MonsterTurn):
            self._erase_combat_status()
            display_turn_separator(outcome.character_name, is_player=False)
            self._process_and_render(
                outcome.prompt, combat=True, turn_scope=outcome.character_id,
            )
            if self.turn_driver.finish_monster_turn(outcome.character_id):
                console.print(f"[dim]{outcome.character_name}'s turn ends.[/dim]")
            if not self.game_state.combat.active:
                self.mode = TurnMode.EXPLORATION
            return

        assert isinstance(outcome, AwaitPlayerInput)
        self._prompt_player_turn(outcome.character_id, outcome.character_name)
        if not self.game_state.combat.active:
            self.mode = TurnMode.EXPLORATION

    def _prompt_player_turn(self, current_id: str, character_name: str) -> None:
        """Collect and dispatch one player combat turn."""
        self._show_combat_status()
        console.print("")
        self._combat_status_lines += 1  # account for the blank line

        try:
            player_input = input(f"[{character_name}'s turn] > ").strip()
        except (KeyboardInterrupt, EOFError):
            raise
        if not player_input:
            self._erase_combat_status()
            return
        # Management screens work in combat too — clear the status bar first
        # so the modal draws on a clean area, then re-render on return.
        if player_input.lower() in _SCREEN_WORDS:
            self._combat_status_lines += 1  # the input line
            self._erase_combat_status()
            self._maybe_open_screen(player_input)
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
        display_turn_separator(character_name, is_player=True)
        self.dm.snapshots.push(f"{character_name}: {player_input[:60]}")
        self._process_and_render(
            f"[{character_name}]: {player_input}",
            combat=True, turn_scope=current_id,
        )
        # Nothing left to spend and the LLM never ended the turn — advance,
        # or this combatant is prompted again forever.
        if self.turn_driver.finish_player_turn(current_id):
            console.print(f"[dim]{character_name}'s turn ends.[/dim]")

    _DEATH_SAVE_STYLES = {
        "died": "bold red",
        "recovered": "bold green",
        "stabilized": "green",
        "stable_skip": "dim",
        "failed": "red",
        "rolled": "yellow",
    }

    def _render_death_save(self, outcome) -> None:
        style = self._DEATH_SAVE_STYLES.get(outcome.kind, "yellow")
        console.print(f"[{style}]{outcome.message}[/{style}]")

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
