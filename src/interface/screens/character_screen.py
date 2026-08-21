"""Interactive character screen.

Browse a party member's full sheet and act on it without memorizing commands:
jump to their inventory, take a short/long rest, or switch characters. The sheet
is rendered as the menu's header so the whole thing is one modal panel. Rests are
resolved engine-side (deterministic, no LLM call) and are disabled during combat.
See ``docs/DESIGN_INVENTORY_UI.md``.
"""
from __future__ import annotations

from typing import Callable

from rich.console import Console

from src.engine import rest as rest_engine
from src.interface.cli import build_character_sheet
from src.interface.cli import console as _default_console
from src.interface.screens.inventory_screen import run_inventory_screen
from src.interface.screens.menu import MenuOption, select


def run_character_screen(
    game_state,
    *,
    console: Console | None = None,
    read_key: Callable[[], str] | None = None,
    char_id: str | None = None,
) -> None:
    """Open the interactive character screen, optionally focused on *char_id*."""
    console = console or _default_console
    player_ids = list(game_state.player_character_ids)
    if not player_ids:
        return
    idx = player_ids.index(char_id) if char_id in player_ids else 0

    while True:
        cid = player_ids[idx]
        char = game_state.get_character(cid)
        sheet = build_character_sheet(char)
        in_combat = game_state.combat.active

        choice = select(
            char.name, _actions(char, player_ids, in_combat),
            console=console, read_key=read_key, header=sheet,
        )
        if choice is None:
            return

        if choice == "inventory":
            run_inventory_screen(game_state, console=console, read_key=read_key, char_id=cid)
        elif choice == "switch":
            picked = _pick_other(game_state, player_ids, cid, console, read_key)
            if picked is not None:
                idx = player_ids.index(picked)
        elif choice == "short_rest":
            _short_rest(char, console, read_key)
        elif choice == "long_rest":
            _long_rest(char, console, read_key)


def _actions(char, player_ids: list[str], in_combat: bool) -> list[MenuOption]:
    opts = [MenuOption(label="Manage inventory", value="inventory")]
    rest_hint = "not while in combat" if in_combat else ""
    opts.append(MenuOption(
        label="Short rest", value="short_rest",
        hint=rest_hint or f"{char.hit_dice_remaining} hit dice",
        enabled=not in_combat and char.hit_dice_remaining > 0,
    ))
    opts.append(MenuOption(
        label="Long rest", value="long_rest", hint=rest_hint, enabled=not in_combat,
    ))
    if len(player_ids) > 1:
        opts.append(MenuOption(label="Switch character", value="switch"))
    return opts


def _pick_other(game_state, player_ids, current_id, console, read_key) -> str | None:
    options = [
        MenuOption(label=game_state.get_character(pid).name, value=pid)
        for pid in player_ids if pid != current_id
    ]
    return select("Switch to", options, console=console, read_key=read_key)


def _short_rest(char, console, read_key) -> None:
    n = char.hit_dice_remaining
    if n <= 0:
        return
    count = select(
        f"Spend how many hit dice? ({char.hit_die_type}, {n} available)",
        [MenuOption(label=str(i), value=i) for i in range(1, n + 1)],
        console=console, read_key=read_key,
    )
    if count is None:
        return
    result = rest_engine.short_rest(char, count)
    if result.get("success"):
        console.print(
            f"  [bold green]{char.name} takes a short rest — heals {result['healed']} HP "
            f"({result['hp_now']}/{char.max_hp}), {result['hit_dice_remaining']} hit dice left.[/bold green]"
        )
    else:
        console.print(f"  [bold red]{result.get('error', 'Rest failed.')}[/bold red]")


def _long_rest(char, console, read_key) -> None:
    confirm = select(
        f"Long rest — {char.name} will be fully restored. Proceed?",
        [MenuOption(label="Yes, take a long rest", value=True),
         MenuOption(label="Cancel", value=False)],
        console=console, read_key=read_key,
    )
    if not confirm:
        return
    result = rest_engine.long_rest(char)
    if result.get("success"):
        console.print(
            f"  [bold green]{char.name} takes a long rest — fully healed ({char.hp}/{char.max_hp}), "
            f"{result['hit_dice_recovered']} hit dice recovered.[/bold green]"
        )
    else:
        console.print(f"  [bold red]{result.get('error', 'Rest failed.')}[/bold red]")
