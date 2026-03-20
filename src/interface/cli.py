"""Rich-based terminal UI with themed styling."""
from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

if TYPE_CHECKING:
    from src.engine.game_state import GameState
    from src.log.event_log import EventEntry


# ---------------------------------------------------------------------------
# Theme — semantic color palette
# ---------------------------------------------------------------------------

DND_THEME = Theme({
    # Narrative & chrome
    "narration.border":  "cyan",
    "narration.title":   "bold cyan",
    "combat.border":     "bold red",

    # Mechanical output (dimmed relative to narrative)
    "mechanical":        "dim",
    "dice.expr":         "yellow",
    "dice.total":        "bold white",
    "dice.crit":         "bold magenta",

    # HP
    "hp.full":           "green",
    "hp.half":           "yellow",
    "hp.critical":       "bold red",

    # Combat results
    "hit":               "bold green",
    "miss":              "bold red",
    "damage":            "bold red",
    "healing":           "bold green",

    # Status
    "condition":         "bold yellow",
    "slot.available":    "bright_blue",
    "slot.spent":        "dim",

    # Separators & transitions
    "separator":         "dim cyan",
    "transition":        "bold bright_cyan",
    "header":            "bold green",
})

console = Console(theme=DND_THEME)


# ---------------------------------------------------------------------------
# Screen utilities
# ---------------------------------------------------------------------------

def clear_screen() -> None:
    """Clear the terminal."""
    os.system("cls" if os.name == "nt" else "clear")


def display_header() -> None:
    """Display the game header with atmospheric banner, centered in terminal."""
    # Raw lines with Rich markup — visible widths: 52, 55, 57, 57, 57, 55, 52, 55, 46
    _raw_lines = [
        ("[dim cyan]░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░[/dim cyan]", 46),
        ("[dim cyan]░░░[/dim cyan]                                              [dim cyan]░░░[/dim cyan]", 55),
        ("[dim cyan]░░[/dim cyan]     [bold bright_cyan]╔╦╗╦ ╦╔╗╔╔═╗╔═╗╔═╗╔╗╔  ╦ ╦╔═╗╔═╗╦  ╦╔═╗╦═╗[/bold bright_cyan]     [dim cyan]░░[/dim cyan]", 57),
        ("[dim cyan]░░[/dim cyan]     [bold bright_cyan] ║║║ ║║║║║ ╦║╣ ║ ║║║║  ║║║║╣ ╠═╣╚╗╔╝║╣ ╠╦╝[/bold bright_cyan]     [dim cyan]░░[/dim cyan]", 57),
        ("[dim cyan]░░[/dim cyan]     [bold bright_cyan]═╩╝╚═╝╝╚╝╚═╝╚═╝╚═╝╝╚╝  ╚╩╝╚═╝╩ ╩ ╚╝ ╚═╝╩╚═[/bold bright_cyan]     [dim cyan]░░[/dim cyan]", 57),
        ("[dim cyan]░░░[/dim cyan]                                              [dim cyan]░░░[/dim cyan]", 55),
        ("[dim cyan]░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░[/dim cyan]", 46),
    ]
    max_w = 57  # widest line (the three text rows)
    term_w = console.width
    console.print()
    for markup, visible_w in _raw_lines:
        pad = max(0, (term_w - max_w) // 2 + (max_w - visible_w) // 2)
        console.print(" " * pad + markup, highlight=False)
    console.print()
    tagline = "Threads of fate are spun. The loom awaits."
    hint = "Type /help for commands"
    pad_tag = max(0, (term_w - len(tagline)) // 2)
    pad_hint = max(0, (term_w - len(hint)) // 2)
    console.print(" " * pad_tag + f"[dim]{tagline}[/dim]", highlight=False)
    console.print(" " * pad_hint + f"[dim italic]{hint}[/dim italic]", highlight=False)
    console.print()


def display_turn_separator(name: str, *, is_player: bool) -> None:
    """Print a Rule-based separator for a combatant's turn."""
    style = "bold cyan" if is_player else "bold red"
    console.print()
    console.print(Rule(f"{name}'s Turn", style=style, characters="─"))
    console.print()


def display_location_transition(location_name: str) -> None:
    """Show a banner when the party moves to a new location."""
    console.print()
    console.print(
        Panel(
            f"[transition]Entering: {location_name}[/transition]",
            box=box.DOUBLE,
            border_style="transition",
            padding=(0, 4),
            expand=False,
        ),
        justify="center",
    )
    console.print()


# ---------------------------------------------------------------------------
# Narrative streaming
# ---------------------------------------------------------------------------

class NarrativeStreamer:
    """Streams narrative text inside a bordered panel with word-wrapping.

    Uses manual ANSI rendering for smooth token-by-token streaming.
    The border style adapts to narration (DOUBLE) or combat (HEAVY).
    """

    _CYAN = "\033[36m"
    _RED = "\033[31m"
    _BOLD_CYAN = "\033[1;36m"
    _BOLD_RED = "\033[1;31m"
    _RESET = "\033[0m"
    _LEFT_MARGIN = 5   # "  │  " — 2 indent + border + 2 padding
    _RIGHT_MARGIN = 3  # "  │" — 2 padding + border

    def __init__(self, location_name: str = "", combat: bool = False) -> None:
        self._location_name = location_name
        self._combat = combat
        self._started = False
        self._col = 0
        self._max_col = 0
        self._word_buf: list[str] = []

        if combat:
            self._color = self._RED
            self._bold_color = self._BOLD_RED
            # Heavy box chars: ┏━┓ ┃ ┗━┛
            self._tl, self._tr = "\u250f", "\u2513"
            self._bl, self._br = "\u2517", "\u251b"
            self._horiz = "\u2501"
            self._vert = "\u2503"
        else:
            self._color = self._CYAN
            self._bold_color = self._BOLD_CYAN
            # Double box chars: ╔═╗ ║ ╚═╝
            self._tl, self._tr = "\u2554", "\u2557"
            self._bl, self._br = "\u255a", "\u255d"
            self._horiz = "\u2550"
            self._vert = "\u2551"

        self._line_prefix = f"  {self._color}{self._vert}{self._RESET}  "
        self._line_suffix = f"  {self._color}{self._vert}{self._RESET}"

    def _close_line(self) -> None:
        """Pad the current line to full width and print the right border."""
        remaining = self._max_col - self._col
        if remaining > 0:
            sys.stdout.write(" " * remaining)
        sys.stdout.write(self._line_suffix)

    def start(self) -> None:
        """Print the top border of the narrative panel."""
        w = console.width - 4
        self._max_col = w - self._RIGHT_MARGIN - 1  # content width inside borders
        if self._location_name:
            label = f" {self._location_name} "
            fill = max(0, w - len(label) - 2)
            sys.stdout.write(
                f"  {self._color}{self._tl}{self._horiz}"
                f"{self._bold_color}{label}"
                f"{self._color}{self._horiz * fill}{self._tr}{self._RESET}\n"
            )
        else:
            sys.stdout.write(
                f"  {self._color}{self._tl}{self._horiz * w}{self._tr}{self._RESET}\n"
            )
        # Empty padding line with both borders, then start first content line
        sys.stdout.write(f"{self._line_prefix}{' ' * self._max_col}{self._line_suffix}\n{self._line_prefix}")
        sys.stdout.flush()
        self._started = True
        self._col = 0

    def _newline(self) -> None:
        self._close_line()
        sys.stdout.write(f"\n{self._line_prefix}")
        self._col = 0

    def _flush_word(self) -> None:
        if not self._word_buf:
            return
        word = "".join(self._word_buf)
        self._word_buf.clear()
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
                if self._col < self._max_col:
                    sys.stdout.write(" ")
                    self._col += 1
                else:
                    self._newline()
            else:
                self._word_buf.append(char)
        # Flush partial word for responsive streaming
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
            self._close_line()
            w = console.width - 4
            # Empty line before bottom border, also with right border
            sys.stdout.write(f"\n{self._line_prefix}")
            sys.stdout.write(" " * self._max_col)
            sys.stdout.write(self._line_suffix)
            sys.stdout.write(
                f"\n  {self._color}{self._bl}{self._horiz * w}{self._br}{self._RESET}\n"
            )
            sys.stdout.flush()
            self._started = False


def display_narrative(text: str, location_name: str = "", combat: bool = False) -> None:
    """Display narrative prose in a styled panel (non-streamed fallback)."""
    if combat:
        title = f"[combat.border]{location_name}[/combat.border]" if location_name else ""
        console.print(Panel(text, title=title, box=box.HEAVY, border_style="combat.border", padding=(1, 2)))
    else:
        title = f"[narration.title]{location_name}[/narration.title]" if location_name else ""
        console.print(Panel(text, title=title, box=box.DOUBLE, border_style="narration.border", padding=(1, 2)))


# ---------------------------------------------------------------------------
# HP bar helper
# ---------------------------------------------------------------------------

def _hp_bar(hp: int, max_hp: int, width: int = 10) -> str:
    """Return a colored HP bar string like '████░░░░ 18/25'."""
    ratio = max(0, min(hp / max_hp, 1.0)) if max_hp > 0 else 0
    filled = round(ratio * width)
    empty = width - filled
    if ratio > 0.5:
        color = "hp.full"
    elif ratio > 0:
        color = "hp.half"
    else:
        color = "hp.critical"
    bar = "█" * filled + "░" * empty
    return f"[{color}]{bar} {hp}/{max_hp}[/{color}]"


def _hp_color(hp: int, max_hp: int) -> str:
    """Return the semantic HP color name."""
    if hp > max_hp // 2:
        return "hp.full"
    return "hp.half" if hp > 0 else "hp.critical"


# ---------------------------------------------------------------------------
# Dice rolls — compact vs expanded
# ---------------------------------------------------------------------------

def display_dice_roll(entry: "EventEntry") -> None:
    """Display a dice roll result: compact for routine, expanded for crits."""
    tool = entry.tool_name
    inputs = entry.inputs
    result = entry.result

    if tool == "roll_dice":
        _display_roll_dice(inputs, result)
    elif tool == "attack":
        _display_attack(inputs, result)
    elif tool == "cast_spell":
        _display_cast_spell(inputs, result)
    elif tool == "ability_check":
        _display_ability_check(inputs, result)
    elif tool == "saving_throw":
        _display_saving_throw(inputs, result)


def _display_roll_dice(inputs: dict, result: dict) -> None:
    expr = inputs.get("dice_expr", "?")
    reason = inputs.get("reason", "")
    rolls = result.get("rolls", [])
    total = result.get("total", "?")
    mod = result.get("modifier", 0)
    roll_str = "+".join(str(r) for r in rolls)
    mod_str = f"{mod:+d}" if mod else ""

    label = f"[dim]{reason}:[/dim] " if reason else ""
    console.print(
        f"  [dim]⊡[/dim] {label}[dice.expr]{expr}[/dice.expr] → "
        f"[{roll_str}]{mod_str} = [dice.total]{total}[/dice.total]"
    )


def _display_attack(inputs: dict, result: dict) -> None:
    attacker = result.get("attacker", inputs.get("attacker_id", "?"))
    target = result.get("target", inputs.get("target_id", "?"))
    rolls = result.get("roll", [])
    bonus = result.get("attack_bonus", 0)
    total = result.get("total_attack", "?")
    ac = result.get("target_ac", "?")
    hits = result.get("hits", False)
    is_crit = result.get("is_crit", False)
    damage = result.get("damage")

    roll_display = "+".join(str(r) for r in (rolls if isinstance(rolls, list) else [rolls]))

    if is_crit:
        # Expanded — critical hit
        hit_str = "[dice.crit]★ CRITICAL HIT[/dice.crit]"
        console.print(f"  ┌ [dim]Attack Roll[/dim] ──")
        console.print(
            f"  │ [dice.expr]1d20+{bonus}[/dice.expr] → [{roll_display}]+{bonus}"
            f" = [dice.total]{total}[/dice.total] vs AC {ac} {hit_str}"
        )
        if damage is not None:
            dmg_type = result.get("damage_type", "")
            hp_left = result.get("hp_remaining", "?")
            console.print(f"  │ Damage: [damage]{damage}[/damage] {dmg_type} | {target} → {hp_left} HP")
        console.print("  └──")
    else:
        # Compact — routine attack
        hit_str = "[hit]✓[/hit]" if hits else "[miss]✗[/miss]"
        dmg_part = ""
        if damage is not None:
            dmg_type = result.get("damage_type", "")
            hp_left = result.get("hp_remaining", "?")
            dmg_part = f" | [damage]{damage}[/damage] {dmg_type} → {hp_left} HP"
        console.print(
            f"  [dim]⚔[/dim] {attacker} → {target}: "
            f"[dice.expr]1d20+{bonus}[/dice.expr] = [dice.total]{total}[/dice.total]"
            f" vs AC {ac} {hit_str}{dmg_part}"
        )


def _display_cast_spell(inputs: dict, result: dict) -> None:
    spell = result.get("spell", inputs.get("spell_name", "?"))
    if not result.get("success"):
        console.print(f"  [dim]✦[/dim] [magenta]{spell}[/magenta] — [miss]failed[/miss]")
        return
    console.print(f"  ┌ [magenta]{spell}[/magenta]")
    for t in result.get("targets", []):
        if "damage" in t:
            console.print(
                f"  │ {t['target']}: [damage]{t.get('damage', 0)}[/damage] dmg"
                f" | {t.get('hp_remaining', '?')} HP remaining"
            )
    if "healed" in result:
        console.print(f"  │ Healed: [healing]{result['healed']}[/healing] HP")
    console.print("  └──")


def _display_ability_check(inputs: dict, result: dict) -> None:
    skill = inputs.get("skill", inputs.get("ability", "?"))
    char = inputs.get("character_id", "?")
    total = result.get("total", "?")
    dc = result.get("dc", "?")
    success = result.get("success")

    mark = "[hit]✓[/hit]" if success else "[miss]✗[/miss]"
    console.print(
        f"  [dim]⊡[/dim] {char} {skill} check: "
        f"[dice.total]{total}[/dice.total] vs DC {dc} {mark}"
    )


def _display_saving_throw(inputs: dict, result: dict) -> None:
    ability = inputs.get("ability", "?")
    char = inputs.get("character_id", "?")
    total = result.get("total", "?")
    dc = result.get("dc", "?")
    success = result.get("success")

    mark = "[hit]✓[/hit]" if success else "[miss]✗[/miss]"
    console.print(
        f"  [dim]⊡[/dim] {char} {ability} save: "
        f"[dice.total]{total}[/dice.total] vs DC {dc} {mark}"
    )


# ---------------------------------------------------------------------------
# Status bar — table with HP bars and slot pips
# ---------------------------------------------------------------------------

def display_status_bar(game_state: "GameState") -> None:
    """Render a multi-column status bar with HP bars and spell slot pips."""
    table = Table(box=None, show_header=False, padding=(0, 2), expand=True)
    for _ in game_state.player_characters:
        table.add_column(justify="center")

    name_row: list[str] = []
    hp_row: list[str] = []
    detail_row: list[str] = []

    for char in game_state.player_characters:
        name_row.append(f"[bold]{char.name}[/bold]")
        hp_row.append(f"{_hp_bar(char.hp, char.max_hp)}  AC {char.ac}")

        parts: list[str] = []
        # Spell slot pips
        if char.spell_slots and char.max_spell_slots:
            for lvl in sorted(char.max_spell_slots):
                total = char.max_spell_slots[lvl]
                remaining = char.spell_slots.get(lvl, 0)
                pips = (
                    "[slot.available]●[/slot.available]" * remaining
                    + "[slot.spent]○[/slot.spent]" * (total - remaining)
                )
                parts.append(f"L{lvl}:{pips}")
        # Conditions
        if char.conditions:
            conds = " ".join(f"[condition]{c}[/condition]" for c in char.conditions)
            parts.append(conds)
        detail_row.append("  ".join(parts) if parts else "")

    table.add_row(*name_row)
    table.add_row(*hp_row)
    if any(detail_row):
        table.add_row(*detail_row)

    console.print(Panel(table, border_style="dim", padding=(0, 1)))


# ---------------------------------------------------------------------------
# Combat initiative tracker — horizontal timeline
# ---------------------------------------------------------------------------

def display_combat_state(game_state: "GameState") -> None:
    """Show initiative order as a horizontal timeline with HP bars."""
    combat = game_state.combat
    if not combat.active:
        return

    # Round header
    console.print(Rule(f"⚔ Round {combat.round}", style="combat.border", characters="─"))

    # Build timeline segments
    segments: list[str] = []
    for i, cid in enumerate(combat.turn_order):
        try:
            char = game_state.get_character(cid)
        except KeyError:
            continue
        c = combat.combatants[cid]
        if char.hp <= 0 or "dead" in char.conditions:
            continue

        hp_bar = _hp_bar(char.hp, char.max_hp, width=6)
        is_active = i == combat.current_turn_index
        cond_str = f" [condition]{','.join(char.conditions)}[/condition]" if char.conditions else ""

        if is_active:
            entry = f"[bold]▶ {char.name}[/bold]({c.initiative:+d}) {hp_bar}{cond_str}"
        else:
            name_style = "cyan" if char.is_player else "red"
            entry = f"[{name_style}]{char.name}[/{name_style}]({c.initiative:+d}) {hp_bar}{cond_str}"

        segments.append(entry)

    timeline = "  →  ".join(segments)
    console.print(Panel(timeline, border_style="combat.border", padding=(0, 1)))
