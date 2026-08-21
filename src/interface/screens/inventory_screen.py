"""Interactive inventory screen.

Drives the :class:`~src.engine.inventory.InventoryController` from keyboard menus:
pick an item, see only the actions legal for it right now (the controller's
``actions_for``), apply one, watch the view update. No game rules live here — the
screen is a thin View over the controller. See ``docs/DESIGN_INVENTORY_UI.md``.
"""
from __future__ import annotations

from typing import Callable

from rich.console import Console

from src.engine.inventory import InventoryController, ItemAction, InventoryView
from src.interface.cli import console as _default_console
from src.interface.screens.menu import MenuOption, select

# Category → glyph, mirrors the static /inventory render.
_ICONS = {
    "weapon": "⚔", "armor": "🛡", "shield": "🛡",
    "consumable": "🧪", "magic": "✨", "gear": "•",
}
# Action → menu label (verb the player reads).
_ACTION_LABELS = {
    ItemAction.EXAMINE: "Examine",
    ItemAction.USE: "Use",
    ItemAction.UNEQUIP: "Unequip",
    ItemAction.DROP: "Drop",
    ItemAction.GIVE: "Give",
    ItemAction.SPLIT: "Split stack",
}


def run_inventory_screen(
    game_state,
    *,
    console: Console | None = None,
    read_key: Callable[[], str] | None = None,
    char_id: str | None = None,
) -> None:
    """Open the interactive inventory. Returns when the player backs all the way out.

    When *char_id* is given (e.g. opened from the character screen), it jumps
    straight to that character and backing out returns immediately rather than
    dropping into the party picker.
    """
    console = console or _default_console
    controller = InventoryController(game_state)
    player_ids = list(game_state.player_character_ids)
    scoped = char_id is not None

    cid = char_id or (player_ids[0] if len(player_ids) == 1 else None)
    while True:
        if cid is None:
            cid = _pick_character(controller, player_ids, console, read_key)
            if cid is None:
                return
        cont = _manage_character(controller, cid, console, read_key)
        if not cont:
            # Backed out: return to picker, or exit when solo / externally scoped.
            if scoped or len(player_ids) == 1:
                return
            cid = None


def _pick_character(
    controller: InventoryController, player_ids: list[str], console, read_key
) -> str | None:
    options = []
    for cid in player_ids:
        view = controller.view(cid)
        options.append(MenuOption(
            label=view.character_name,
            value=cid,
            hint=f"{view.gold} gp · {len([i for i in view.items if not i.equipped])} items",
        ))
    return select("Whose inventory?", options, console=console, read_key=read_key)


def _manage_character(controller: InventoryController, char_id: str, console, read_key) -> bool:
    """Item-selection loop for one character. Returns False when the player backs out."""
    while True:
        view = controller.view(char_id)
        options = _item_options(view)
        if not options:
            console.print(f"  [dim]{view.character_name} is carrying nothing.[/dim]")
            return False
        item_id = select(_title(view), options, console=console, read_key=read_key)
        if item_id is None:
            return False
        _act_on_item(controller, char_id, item_id, console, read_key)


def _title(view: InventoryView) -> str:
    enc = f" · {view.carry_weight:g}/{view.capacity:g} lb"
    if view.encumbrance_tier != "normal":
        enc += f" ({view.encumbrance_tier})"
    attune = f" · attuned {view.attunement_used}/{view.attunement_max}" if view.attunement_used else ""
    return f"{view.character_name} — {view.gold} gp{enc}{attune}"


def _item_options(view: InventoryView) -> list[MenuOption]:
    options = []
    for item in view.items:
        icon = _ICONS.get(item.category.value, "•")
        qty = f" x{item.quantity}" if item.quantity > 1 else ""
        tags = []
        if item.equipped:
            tags.append("equipped")
        if item.category.value == "consumable":
            tags.append("usable")
        options.append(MenuOption(
            label=f"{icon} {item.name}{qty}",
            value=item.id,
            hint=" · ".join(tags),
        ))
    return options


def _act_on_item(controller: InventoryController, char_id: str, item_id: str, console, read_key) -> None:
    actions = controller.actions_for(char_id, item_id)
    if not actions:
        return
    options = [MenuOption(label=_ACTION_LABELS.get(a, a.value.title()), value=a) for a in actions]
    action = select("Action", options, console=console, read_key=read_key,
                    footer="↑/↓ move · Enter do · Esc back")
    if action is None:
        return

    # Least-destructive defaults for quantity-bearing actions; a future revision
    # can prompt for an amount. SPLIT is a staging no-op on legacy storage.
    kwargs = {}
    if action in (ItemAction.GIVE, ItemAction.DROP, ItemAction.SPLIT):
        kwargs["quantity"] = 1
    result = controller.apply(char_id, action, item_id, **kwargs)

    if result.success:
        console.print(f"  [bold green]{result.message}[/bold green]" if action == ItemAction.USE
                      else f"  [bold]{result.message}[/bold]")
    else:
        console.print(f"  [bold red]{result.error}[/bold red]")
