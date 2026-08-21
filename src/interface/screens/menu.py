"""Reusable keyboard-driven menu primitive.

The load-bearing piece both inventory and character screens sit on: render a
list of options, move a cursor with the arrow keys (or j/k), select with Enter,
back out with Esc. Pure View — it returns the chosen value and never touches
game state.

Key reading is injectable (``read_key``) so the navigation logic is unit-tested
without a TTY and without requiring ``readchar`` at test time. ``readchar`` is
imported lazily; :func:`interactive_enabled` is the guard callers check before
opening a screen, falling back to the static command path otherwise (so the
headless debug agent and CI, which run under piped stdin, are unaffected).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable

from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from src.interface.cli import console as _default_console


@dataclass
class MenuOption:
    """One selectable row. ``value`` is returned when the row is chosen."""

    label: str           # Rich markup shown on the left
    value: Any
    hint: str = ""       # dim, right-aligned (e.g. an action count or status)
    enabled: bool = True


# Semantic actions the loop understands, decoupled from raw key bytes.
_SEMANTIC = {"up", "down", "enter", "cancel", "home", "end"}


def interactive_status() -> tuple[bool, str]:
    """Whether interactive screens can run, with a human reason when they can't.

    Requires a real TTY on both ends (the menu reads keys and animates) and an
    importable ``readchar``. The reason string lets callers tell the player *why*
    they got the static fallback instead of silently degrading.
    """
    if not sys.stdin.isatty():
        return False, "input is not an interactive terminal"
    if not sys.stdout.isatty():
        return False, "output is not an interactive terminal"
    try:
        import readchar  # noqa: F401
    except ImportError:
        return False, "the 'readchar' package is not installed (pip install readchar)"
    return True, ""


def interactive_enabled() -> bool:
    """True only when we have a real TTY *and* ``readchar`` is importable."""
    return interactive_status()[0]


def _assemble_key(read1: Callable[[], str], more_available: Callable[[], bool]) -> str:
    """Build one logical key from raw chars, returning a lone Esc immediately.

    ``read1`` reads a single char (blocking); ``more_available`` reports whether
    another char is already waiting. This is the fix for the readchar gotcha:
    ``readchar.readkey()`` reads ``\\x1b`` and then *blocks* trying to complete an
    escape sequence, so a bare Esc hangs until the next keypress. Here, if nothing
    follows the Esc, we treat it as Esc; only when a ``[``/``O`` follows do we read
    the rest of a CSI sequence (arrow keys, Home/End).
    """
    ch = read1()
    if ch != "\x1b":
        return ch
    if not more_available():
        return "\x1b"
    ch2 = read1()
    if ch2 in "[O":
        return ch + ch2 + read1()
    return ch + ch2


def _default_read_key() -> str:
    """Read one keypress. POSIX path handles the lone-Esc case; Windows defers to
    readchar (where arrow keys don't start with Esc, so the gotcha doesn't apply)."""
    if sys.platform == "win32":  # pragma: no cover - platform-specific
        import readchar
        return readchar.readkey()

    import os
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # Read raw bytes off the fd (not buffered sys.stdin.read, which would read
        # ahead and swallow the rest of an escape sequence past select's view).
        return _assemble_key(
            lambda: os.read(fd, 1).decode("utf-8", "replace"),
            lambda: bool(select.select([fd], [], [], 0.05)[0]),
        )
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _semantic(raw: str) -> str:
    """Normalize a raw key (or a test token) to a semantic action or the char."""
    if raw in _SEMANTIC:
        return raw
    try:
        from readchar import key as K
    except ImportError:  # pragma: no cover - only when dep missing
        K = None
    if K is not None:
        if raw in (K.UP, K.CTRL_P):
            return "up"
        if raw in (K.DOWN, K.CTRL_N):
            return "down"
        if raw in (K.ENTER, getattr(K, "CR", "\r"), getattr(K, "LF", "\n")):
            return "enter"
        if raw in (K.ESC, K.HOME):
            return "cancel" if raw == K.ESC else "home"
        if raw == K.END:
            return "end"
    if raw in ("k",):
        return "up"
    if raw in ("j",):
        return "down"
    if raw in ("\r", "\n"):
        return "enter"
    if raw in ("\x1b", "q", "Q"):
        return "cancel"
    return raw


def _first_enabled(options: list[MenuOption], start: int, step: int) -> int:
    """Index of the next enabled option from *start* moving by *step* (wraps)."""
    n = len(options)
    for offset in range(1, n + 1):
        idx = (start + step * offset) % n
        if options[idx].enabled:
            return idx
    return start


def _render(title: str, options: list[MenuOption], cursor: int, footer: str,
            header: Any = None) -> Panel:
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(width=2, no_wrap=True)         # cursor
    table.add_column(ratio=1)                        # label
    table.add_column(justify="right", no_wrap=True)  # hint
    for i, opt in enumerate(options):
        selected = i == cursor
        caret = "[bold bright_cyan]▸[/bold bright_cyan]" if selected else " "
        if not opt.enabled:
            label = f"[dim]{opt.label}[/dim]"
        elif selected:
            label = f"[bold]{opt.label}[/bold]"
        else:
            label = opt.label
        hint = f"[dim]{opt.hint}[/dim]" if opt.hint else ""
        table.add_row(caret, label, hint)
    parts: list[Any] = []
    if header is not None:
        # Accept a markup string or any Rich renderable, shown above the options.
        parts.append(Text.from_markup(header) if isinstance(header, str) else header)
        parts.append(Rule(style="dim cyan"))
    parts.extend([table, Text(footer, style="dim", justify="center")])
    # Literal styles (not theme names) so the menu renders on any Console.
    return Panel(Group(*parts), title=f"[bold green]{title}[/bold green]", border_style="dim cyan")


def select(
    title: str,
    options: list[MenuOption],
    *,
    console: Console | None = None,
    read_key: Callable[[], str] | None = None,
    footer: str = "↑/↓ move · Enter select · Esc back",
    header: Any = None,
) -> Any | None:
    """Show a modal menu; return the chosen option's ``value`` or ``None``.

    *header* (a markup string or Rich renderable) is shown above the options —
    e.g. a character sheet the action menu acts on. Renders transiently (the menu
    erases itself on exit) so the surrounding prompt flow is left clean.
    """
    if not options:
        return None
    console = console or _default_console
    read_key = read_key or _default_read_key

    cursor = 0 if options[0].enabled else _first_enabled(options, 0, 1)

    from rich.live import Live

    with Live(
        _render(title, options, cursor, footer, header),
        console=console, transient=True, auto_refresh=False, screen=False,
    ) as live:
        while True:
            live.update(_render(title, options, cursor, footer, header))
            live.refresh()
            action = _semantic(read_key())
            if action == "up":
                cursor = _first_enabled(options, cursor, -1)
            elif action == "down":
                cursor = _first_enabled(options, cursor, 1)
            elif action == "home":
                cursor = _first_enabled(options, len(options) - 1, 1)
            elif action == "end":
                cursor = _first_enabled(options, 0, -1)
            elif action == "enter":
                if options[cursor].enabled:
                    return options[cursor].value
            elif action == "cancel":
                return None
