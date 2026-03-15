"""Rich-based terminal UI."""
from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

if TYPE_CHECKING:
    from src.engine.game_state import GameState
    from src.log.event_log import EventEntry

console = Console()


def clear_screen() -> None:
    """Clear the terminal."""
    os.system("cls" if os.name == "nt" else "clear")


def display_header() -> None:
    """Display the game header after clearing."""
    console.print("[bold green]═══ AI Dungeon Master ═══[/bold green]")
    console.print("[dim]Commands: quit | /recap[/dim]\n")


class NarrativeStreamer:
    """Streams narrative text inside a bordered panel with word-wrapping."""

    _CYAN = "\033[36m"
    _RESET = "\033[0m"
    _BOLD_CYAN = "\033[1;36m"
    # "  │  " — 2 indent + border + 2 padding = 5 visible chars
    _LINE_PREFIX = f"  {_CYAN}\u2502{_RESET}  "
    _MARGIN = 5  # visible character width of the prefix

    def __init__(self, location_name: str = "") -> None:
        self._location_name = location_name
        self._started = False
        self._col = 0  # current column position on the line
        self._max_col = 0  # computed in start()
        self._word_buf: list[str] = []  # buffer for current word

    def start(self) -> None:
        """Print the top border of the narrative panel."""
        w = console.width - 4
        self._max_col = console.width - self._MARGIN - 1  # leave 1 char margin
        if self._location_name:
            label = f" {self._location_name} "
            fill = max(0, w - len(label) - 2)
            sys.stdout.write(f"  {self._CYAN}\u256d\u2500{self._BOLD_CYAN}{label}{self._CYAN}{'─' * fill}\u256e{self._RESET}\n")
        else:
            sys.stdout.write(f"  {self._CYAN}\u256d{'─' * w}\u256e{self._RESET}\n")
        sys.stdout.write(f"{self._LINE_PREFIX}\n{self._LINE_PREFIX}")
        sys.stdout.flush()
        self._started = True
        self._col = 0

    def _newline(self) -> None:
        """Write a line break with the border prefix."""
        sys.stdout.write(f"\n{self._LINE_PREFIX}")
        self._col = 0

    def _flush_word(self) -> None:
        """Flush the buffered word, wrapping to next line if needed."""
        if not self._word_buf:
            return
        word = "".join(self._word_buf)
        self._word_buf.clear()
        # If the word would overflow, wrap first (unless we're at line start)
        if self._col > 0 and self._col + len(word) > self._max_col:
            self._newline()
        sys.stdout.write(word)
        self._col += len(word)

    def write_chunk(self, text: str) -> None:
        """Write a chunk of streamed text with word-wrapping."""
        if not self._started:
            self.start()
        for char in text:
            if char == "\n":
                self._flush_word()
                self._newline()
            elif char == " ":
                self._flush_word()
                # Write the space if it fits, otherwise it becomes the wrap point
                if self._col < self._max_col:
                    sys.stdout.write(" ")
                    self._col += 1
                else:
                    self._newline()
            else:
                self._word_buf.append(char)
        # Flush partial word so text appears immediately during streaming
        if self._word_buf:
            word = "".join(self._word_buf)
            if self._col > 0 and self._col + len(word) > self._max_col:
                self._newline()
            sys.stdout.write(word)
            self._col += len(word)
            self._word_buf.clear()
        sys.stdout.flush()

    def end(self) -> None:
        """Print the bottom border of the narrative panel."""
        if self._started:
            self._flush_word()
            w = console.width - 4
            sys.stdout.write(f"\n{self._LINE_PREFIX}\n  {self._CYAN}\u2570{'─' * w}\u256f{self._RESET}\n")
            sys.stdout.flush()
            self._started = False


def display_narrative(text: str, location_name: str = "") -> None:
    """Display narrative prose in a styled panel (non-streamed fallback)."""
    title = f"[bold cyan]{location_name}[/bold cyan]" if location_name else ""
    console.print(Panel(text, title=title, border_style="cyan", padding=(1, 2)))


def display_dice_roll(entry: "EventEntry") -> None:
    """Display a dice roll result as a compact callout box."""
    tool = entry.tool_name
    inputs = entry.inputs
    result = entry.result

    if tool == "roll_dice":
        expr = inputs.get("dice_expr", "?")
        reason = inputs.get("reason", "")
        rolls = result.get("rolls", [])
        total = result.get("total", "?")
        mod = result.get("modifier", 0)
        roll_str = "+".join(str(r) for r in rolls)
        mod_str = f"{mod:+d}" if mod else ""
        line = f"[yellow]{expr}[/yellow] \u2192 [{roll_str}]{mod_str} = [bold]{total}[/bold]"
        if reason:
            line = f"[dim]{reason}:[/dim] " + line
        console.print(f"  \u250c {line}")

    elif tool == "attack":
        attacker = result.get("attacker", inputs.get("attacker_id", "?"))
        target = result.get("target", inputs.get("target_id", "?"))
        rolls = result.get("roll", [])
        bonus = result.get("attack_bonus", 0)
        total = result.get("total_attack", "?")
        ac = result.get("target_ac", "?")
        hits = result.get("hits", False)
        is_crit = result.get("is_crit", False)
        damage = result.get("damage")

        hit_str = "[bold green]\u2713 HIT[/bold green]" if hits else "[bold red]\u2717 MISS[/bold red]"
        if is_crit:
            hit_str = "[bold magenta]\u2605 CRITICAL HIT[/bold magenta]"
        roll_display = "+".join(str(r) for r in (rolls if isinstance(rolls, list) else [rolls]))
        line = f"[yellow]1d20+{bonus}[/yellow] \u2192 [{roll_display}]+{bonus} = [bold]{total}[/bold] vs AC {ac} {hit_str}"
        console.print(f"  \u250c Attack Roll \u2500\u2500")
        console.print(f"  \u2502 {line}")
        if damage is not None:
            dmg_type = result.get("damage_type", "")
            hp_left = result.get("hp_remaining", "?")
            console.print(f"  \u2502 Damage: [bold red]{damage}[/bold red] {dmg_type} | {target} \u2192 {hp_left} HP")
        console.print("  \u2514\u2500\u2500")

    elif tool in ("cast_spell",):
        spell = result.get("spell", inputs.get("spell_name", "?"))
        if result.get("success"):
            targets_info = result.get("targets", [])
            console.print(f"  \u250c [magenta]{spell}[/magenta]")
            for t in targets_info:
                if "damage" in t:
                    console.print(f"  \u2502 {t['target']}: {t.get('damage', 0)} dmg | {t.get('hp_remaining', '?')} HP remaining")
                elif "healed" in result:
                    console.print(f"  \u2502 Healed: {result['healed']} HP")
            console.print("  \u2514\u2500\u2500")


def display_status_bar(game_state: "GameState") -> None:
    """Compact HP/slots footer for all player characters."""
    parts = []
    for char in game_state.player_characters:
        hp_color = "green" if char.hp > char.max_hp // 2 else ("yellow" if char.hp > 0 else "red")
        hp_str = f"[{hp_color}]{char.hp}/{char.max_hp} HP[/{hp_color}]"
        slot_str = ""
        if char.spell_slots:
            slot_str = " | Slots: " + " ".join(
                f"L{k}:{v}" for k, v in sorted(char.spell_slots.items()) if v > 0
            )
        cond_str = ""
        if char.conditions:
            cond_str = f" [{', '.join(char.conditions)}]"
        parts.append(f"[bold]{char.name}[/bold] AC {char.ac} {hp_str}{slot_str}{cond_str}")

    console.print(Panel(" | ".join(parts), border_style="dim", padding=(0, 1)))


def display_combat_state(game_state: "GameState") -> None:
    """Show initiative order with HP during combat."""
    combat = game_state.combat
    if not combat.active:
        return

    lines = [f"[bold red]COMBAT \u2014 Round {combat.round}[/bold red]", ""]
    for i, cid in enumerate(combat.turn_order):
        try:
            char = game_state.get_character(cid)
        except KeyError:
            continue
        c = combat.combatants[cid]
        marker = "[bold cyan]\u2192[/bold cyan] " if i == combat.current_turn_index else "  "
        actions = []
        if c.has_action:
            actions.append("A")
        if c.has_bonus_action:
            actions.append("B")
        hp_color = "green" if char.hp > char.max_hp // 2 else ("yellow" if char.hp > 0 else "red")
        hp_str = f"[{hp_color}]{char.hp}/{char.max_hp}[/{hp_color}]"
        cond_str = f" [{', '.join(char.conditions)}]" if char.conditions else ""
        action_str = f"[{'/'.join(actions)}]" if actions else "[spent]"
        lines.append(f"{marker}[bold]{char.name}[/bold] (Init {c.initiative:+d}) {hp_str} HP {action_str}{cond_str}")

    console.print(Panel("\n".join(lines), border_style="red", padding=(0, 1)))
