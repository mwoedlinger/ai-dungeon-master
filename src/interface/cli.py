"""Rich-based terminal UI."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

if TYPE_CHECKING:
    from src.engine.game_state import GameState
    from src.log.event_log import EventEntry

console = Console()


def display_narrative(text: str, location_name: str = "") -> None:
    """Display narrative prose in a styled panel."""
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
        line = f"[yellow]{expr}[/yellow] → [{roll_str}]{mod_str} = [bold]{total}[/bold]"
        if reason:
            line = f"[dim]{reason}:[/dim] " + line
        console.print(f"  ┌ {line}")

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

        hit_str = "[bold green]✓ HIT[/bold green]" if hits else "[bold red]✗ MISS[/bold red]"
        if is_crit:
            hit_str = "[bold magenta]★ CRITICAL HIT[/bold magenta]"
        roll_display = "+".join(str(r) for r in (rolls if isinstance(rolls, list) else [rolls]))
        line = f"[yellow]1d20+{bonus}[/yellow] → [{roll_display}]+{bonus} = [bold]{total}[/bold] vs AC {ac} {hit_str}"
        console.print(f"  ┌ Attack Roll ──")
        console.print(f"  │ {line}")
        if damage is not None:
            dmg_type = result.get("damage_type", "")
            hp_left = result.get("hp_remaining", "?")
            console.print(f"  │ Damage: [bold red]{damage}[/bold red] {dmg_type} | {target} → {hp_left} HP")
        console.print("  └──")

    elif tool in ("cast_spell",):
        spell = result.get("spell", inputs.get("spell_name", "?"))
        if result.get("success"):
            targets_info = result.get("targets", [])
            console.print(f"  ┌ [magenta]{spell}[/magenta]")
            for t in targets_info:
                if "damage" in t:
                    console.print(f"  │ {t['target']}: {t.get('damage', 0)} dmg | {t.get('hp_remaining', '?')} HP remaining")
                elif "healed" in result:
                    console.print(f"  │ Healed: {result['healed']} HP")
            console.print("  └──")


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

    lines = [f"[bold red]COMBAT — Round {combat.round}[/bold red]", ""]
    for i, cid in enumerate(combat.turn_order):
        try:
            char = game_state.get_character(cid)
        except KeyError:
            continue
        c = combat.combatants[cid]
        marker = "[bold cyan]→[/bold cyan] " if i == combat.current_turn_index else "  "
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
