"""Slash commands — local actions that bypass the LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.interface.cli import console

if TYPE_CHECKING:
    from src.dm.dungeon_master import DungeonMaster
    from src.engine.game_state import GameState


# Cache for /location descriptions (keyed by location_id)
_location_cache: dict[str, str] = {}


@dataclass
class CommandContext:
    """Everything a command handler might need."""
    game_state: GameState
    dm: DungeonMaster
    save_path: str
    # Set by the session manager when the command signals an exit
    should_exit: bool = False
    should_save: bool = False


def clear_location_cache() -> None:
    """Clear cached /location descriptions (e.g. on location change)."""
    _location_cache.clear()


# ---------------------------------------------------------------------------
# Individual command handlers
# ---------------------------------------------------------------------------

def _cmd_help(args: str, ctx: CommandContext) -> None:
    """Show available commands."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")
    for name, (_, desc) in sorted(COMMANDS.items()):
        table.add_row(f"/{name}", desc)
    # Dynamic character name commands
    for char in ctx.game_state.player_characters:
        table.add_row(f"/{char.name.split()[0].lower()}", f"Show {char.name}'s character sheet")
    console.print(Panel(table, title="[bold]Commands[/bold]", border_style="dim"))


def _cmd_save(args: str, ctx: CommandContext) -> None:
    """Save the current game."""
    ctx.game_state.save(ctx.save_path)
    console.print(f"[green]Game saved to {ctx.save_path}[/green]")


def _cmd_exit(args: str, ctx: CommandContext) -> None:
    """Quit without saving."""
    ctx.should_exit = True
    console.print("[dim]Exiting without saving.[/dim]")


def _cmd_quit(args: str, ctx: CommandContext) -> None:
    """Save and quit."""
    ctx.game_state.save(ctx.save_path)
    console.print(f"[green]Game saved to {ctx.save_path}[/green]")
    ctx.should_exit = True


def _cmd_status(args: str, ctx: CommandContext) -> None:
    """Show party status (HP, AC, conditions)."""
    for char in ctx.game_state.player_characters:
        hp_color = "green" if char.hp > char.max_hp // 2 else ("yellow" if char.hp > 0 else "red")
        cond = f"  [{', '.join(char.conditions)}]" if char.conditions else ""
        slots = ""
        if char.spell_slots:
            used = {k: char.max_spell_slots.get(k, 0) - v for k, v in char.spell_slots.items()}
            slot_parts = [f"L{k}: {v}/{char.max_spell_slots.get(k, 0)}" for k, v in sorted(char.spell_slots.items())]
            slots = " | Slots: " + ", ".join(slot_parts)
        console.print(
            f"  [bold]{char.name}[/bold]  "
            f"[{hp_color}]{char.hp}/{char.max_hp} HP[/{hp_color}]  "
            f"AC {char.ac}{slots}{cond}"
        )


def _cmd_map(args: str, ctx: CommandContext) -> None:
    """Show current location and connections."""
    world = ctx.game_state.world
    loc = world.locations.get(world.current_location_id)
    if not loc:
        console.print("[red]Unknown current location.[/red]")
        return
    console.print(f"\n  [bold cyan]{loc.name}[/bold cyan]")
    console.print(f"  [dim]{loc.description[:120]}...[/dim]\n" if len(loc.description) > 120 else f"  [dim]{loc.description}[/dim]\n")
    if loc.connected_to:
        console.print("  [bold]Exits:[/bold]")
        for cid in loc.connected_to:
            connected = world.locations.get(cid)
            name = connected.name if connected else cid
            console.print(f"    → {name} [dim]({cid})[/dim]")
    console.print()


def _cmd_quests(args: str, ctx: CommandContext) -> None:
    """Show active and completed quests."""
    quests = ctx.game_state.world.quests
    if not quests:
        console.print("[dim]No quests tracked.[/dim]")
        return
    for q in quests:
        icon = {"active": "●", "completed": "✓", "failed": "✗"}.get(q.status, "?")
        color = {"active": "yellow", "completed": "green", "failed": "red"}.get(q.status, "dim")
        console.print(f"  [{color}]{icon}[/{color}] [bold]{q.title}[/bold] [{color}]({q.status})[/{color}]")
        console.print(f"    {q.description}")
        if q.completed_objectives:
            for obj in q.completed_objectives:
                console.print(f"    [green]  ✓ {obj}[/green]")


def _cmd_inventory(args: str, ctx: CommandContext) -> None:
    """Show inventory for all player characters."""
    for char in ctx.game_state.player_characters:
        console.print(f"\n  [bold]{char.name}'s Inventory:[/bold]")
        if not char.inventory:
            console.print("    [dim]Empty[/dim]")
            continue
        for item in char.inventory:
            qty = f" x{item.quantity}" if item.quantity > 1 else ""
            console.print(f"    • {item.name}{qty}")


def _cmd_location(args: str, ctx: CommandContext) -> None:
    """Show/generate a description of the current location."""
    world = ctx.game_state.world
    loc_id = world.current_location_id
    loc = world.locations.get(loc_id)
    if not loc:
        console.print("[red]Unknown current location.[/red]")
        return

    if loc_id in _location_cache:
        console.print(Panel(_location_cache[loc_id], title=f"[bold cyan]{loc.name}[/bold cyan]", border_style="cyan"))
        return

    # Generate a richer description via the LLM
    console.print("[dim]Generating location description...[/dim]")
    prompt = (
        f"[System: The player used /location. Describe the current location '{loc.name}' "
        f"in 2-3 vivid paragraphs. Base description: {loc.description}. "
        f"Include sensory details — what do they see, hear, smell? "
        f"Do NOT advance the story or introduce new events. Just paint the scene.]"
    )
    description = ctx.dm.process_player_input(prompt)
    _location_cache[loc_id] = description
    console.print(Panel(description, title=f"[bold cyan]{loc.name}[/bold cyan]", border_style="cyan"))


def _cmd_journal(args: str, ctx: CommandContext) -> None:
    """Show the world journal — recorded events and NPC attitudes."""
    journal = ctx.game_state.journal

    lines: list[str] = []

    # Global summary
    if journal.global_summary:
        lines.append("[bold]Story So Far[/bold]")
        lines.append(journal.global_summary)
        lines.append("")

    # NPC attitudes
    if journal.npc_attitudes:
        lines.append("[bold]NPC Attitudes[/bold]")
        for npc_id, att in journal.npc_attitudes.items():
            color = {"friendly": "green", "neutral": "yellow", "hostile": "red", "fearful": "magenta"}.get(att.disposition, "dim")
            note = f" — {att.notes}" if att.notes else ""
            lines.append(f"  [{color}]{npc_id}: {att.disposition}[/{color}]{note}")
        lines.append("")

    # World flags
    if journal.world_flags:
        lines.append("[bold]World Flags[/bold]")
        for flag, value in journal.world_flags.items():
            lines.append(f"  {flag}: {value}")
        lines.append("")

    # Recent events
    recent = journal.get_recent_entries(limit=15)
    if recent:
        lines.append("[bold]Recent Events[/bold]")
        for e in recent:
            icon = "★" if e.importance == "major" else "·"
            loc = f" [{e.location_id}]" if e.location_id else ""
            lines.append(f"  {icon} {e.event}{loc}")

    if not lines:
        console.print("[dim]No journal entries yet.[/dim]")
        return

    console.print(Panel("\n".join(lines), title="[bold]World Journal[/bold]", border_style="cyan", padding=(1, 2)))


def _cmd_recap(args: str, ctx: CommandContext) -> None:
    """Generate a narrative recap of the session so far."""
    console.print("[dim]Generating session recap...[/dim]")
    recap = ctx.dm.generate_session_recap()
    console.print(Panel(recap, title="[bold]Session Recap[/bold]", border_style="cyan"))


def _show_character_sheet(char_id: str, ctx: CommandContext) -> None:
    """Display a full character sheet for a player character."""
    try:
        char = ctx.game_state.get_character(char_id)
    except KeyError:
        console.print(f"[red]Character not found: {char_id}[/red]")
        return

    hp_color = "green" if char.hp > char.max_hp // 2 else ("yellow" if char.hp > 0 else "red")

    lines: list[str] = []
    lines.append(f"[bold]{char.name}[/bold]")
    header = f"{char.race} {char.class_name}{f' ({char.subclass})' if char.subclass else ''} — Level {char.level}"
    if char.background:
        header += f" | {char.background}"
    if char.alignment:
        header += f" | {char.alignment}"
    lines.append(header)
    lines.append(f"XP: {char.xp}")
    # Personality
    if any([char.personality_traits, char.ideals, char.bonds, char.flaws]):
        lines.append("")
        if char.personality_traits:
            lines.append(f"  Traits: {char.personality_traits}")
        if char.ideals:
            lines.append(f"  Ideals: {char.ideals}")
        if char.bonds:
            lines.append(f"  Bonds: {char.bonds}")
        if char.flaws:
            lines.append(f"  Flaws: {char.flaws}")
    lines.append("")

    # Ability scores
    scores = char.ability_scores
    lines.append("[bold]Ability Scores[/bold]")
    for ab in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
        val = getattr(scores, ab)
        mod = (val - 10) // 2
        prof = " *" if ab in char.saving_throw_proficiencies else ""
        lines.append(f"  {ab}: {val:2d} ({mod:+d}){prof}")
    lines.append("")

    # Combat stats
    lines.append("[bold]Combat[/bold]")
    lines.append(f"  HP: [{hp_color}]{char.hp}/{char.max_hp}[/{hp_color}]" + (f" (+{char.temp_hp} temp)" if char.temp_hp else ""))
    lines.append(f"  AC: {char.ac}  Speed: {char.speed} ft.")
    lines.append(f"  Proficiency: +{char.proficiency_bonus}")
    lines.append(f"  Hit Dice: {char.hit_dice_remaining}{char.hit_die_type}")
    if char.conditions:
        lines.append(f"  Conditions: {', '.join(char.conditions)}")
    lines.append("")

    # Skills
    if char.skill_proficiencies:
        lines.append("[bold]Skills[/bold]")
        lines.append(f"  {', '.join(char.skill_proficiencies)}")
        lines.append("")

    # Weapons
    if char.weapons:
        lines.append("[bold]Weapons[/bold]")
        for w in char.weapons:
            props = f" ({', '.join(w.properties)})" if w.properties else ""
            lines.append(f"  • {w.name}: {w.damage_dice} {w.damage_type}{props}")
        lines.append("")

    # Armor
    if char.armor:
        lines.append("[bold]Armor[/bold]")
        lines.append(f"  {char.armor.name} (AC {char.armor.base_ac}, {char.armor.armor_type})")
        lines.append("")

    # Spells
    if char.known_spells:
        lines.append("[bold]Spells[/bold]")
        if char.spellcasting_ability:
            dc = char.spell_save_dc
            lines.append(f"  Casting: {char.spellcasting_ability}  Save DC: {dc}")
        if char.spell_slots:
            slot_parts = [f"L{k}: {v}/{char.max_spell_slots.get(k, 0)}" for k, v in sorted(char.spell_slots.items())]
            lines.append(f"  Slots: {', '.join(slot_parts)}")
        lines.append(f"  Known: {', '.join(char.known_spells)}")
        lines.append("")

    # Class resources
    if char.class_resources:
        lines.append("[bold]Class Resources[/bold]")
        for k, v in char.class_resources.items():
            lines.append(f"  {k}: {v}")
        lines.append("")

    # Inventory
    if char.inventory:
        lines.append("[bold]Inventory[/bold]")
        for item in char.inventory:
            qty = f" x{item.quantity}" if item.quantity > 1 else ""
            lines.append(f"  • {item.name}{qty}")

    console.print(Panel("\n".join(lines), border_style="cyan", padding=(1, 2)))


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

# name -> (handler, description)
COMMANDS: dict[str, tuple] = {
    "help":      (_cmd_help,      "Show this help message"),
    "save":      (_cmd_save,      "Save the current game"),
    "exit":      (_cmd_exit,      "Quit without saving"),
    "quit":      (_cmd_quit,      "Save and quit"),
    "q":         (_cmd_quit,      "Save and quit (alias)"),
    "status":    (_cmd_status,    "Show party HP, AC, and conditions"),
    "map":       (_cmd_map,       "Show current location and exits"),
    "quests":    (_cmd_quests,    "Show quest log"),
    "inventory": (_cmd_inventory, "Show party inventory"),
    "inv":       (_cmd_inventory, "Show party inventory (alias)"),
    "location":  (_cmd_location,  "Describe current location (cached)"),
    "journal":   (_cmd_journal,   "Show world journal and NPC attitudes"),
    "recap":     (_cmd_recap,     "Narrative recap of the session"),
}


def try_handle_command(raw_input: str, ctx: CommandContext) -> bool:
    """Try to handle input as a slash command. Returns True if handled."""
    if not raw_input.startswith("/"):
        return False

    parts = raw_input[1:].split(None, 1)
    cmd_name = parts[0].lower() if parts else ""
    cmd_args = parts[1] if len(parts) > 1 else ""

    # Check static commands
    if cmd_name in COMMANDS:
        handler, _ = COMMANDS[cmd_name]
        handler(cmd_args, ctx)
        return True

    # Check dynamic character name commands: /firstname
    for char in ctx.game_state.player_characters:
        first_name = char.name.split()[0].lower()
        if cmd_name == first_name:
            _show_character_sheet(char.id, ctx)
            return True

    console.print(f"[red]Unknown command: /{cmd_name}[/red]  Type [bold]/help[/bold] for available commands.")
    return True
