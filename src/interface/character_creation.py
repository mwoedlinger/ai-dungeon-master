"""Interactive character creation wizard using Rich CLI."""
from __future__ import annotations

import re

from rich.console import Console
from rich.table import Table

from src.engine.progression import ALIGNMENTS, BACKGROUNDS, CLASS_TEMPLATES, RACES, get_spell_slots_for_level
from src.engine.rules import proficiency_bonus_for_level
from src.models.character import AbilityScores, Armor, Character, Weapon

console = Console()

# Standard array in priority order
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]
ABILITY_ORDER = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]


def _slugify(name: str) -> str:
    """Create a simple ID from a character name."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _pick(prompt: str, options: list[str], default: str | None = None) -> str:
    """Ask the user to pick from a list, with optional default."""
    opt_lower = [o.lower() for o in options]
    display_options = ", ".join(options)
    while True:
        suffix = f" [{default}]" if default else ""
        raw = console.input(f"[bold]{prompt}[/bold] ({display_options}){suffix}: ").strip()
        if not raw and default:
            return default
        if raw.lower() in opt_lower:
            return options[opt_lower.index(raw.lower())]
        console.print(f"[red]  Invalid choice. Please pick from: {display_options}[/red]")


def _assign_stats(class_name: str) -> dict[str, int]:
    """Assign standard array to abilities in class-priority order, with optional reorder."""
    template = CLASS_TEMPLATES[class_name]
    priority = template["primary"]  # e.g. ["STR", "CON", "DEX", "WIS", "CHA", "INT"]

    default_assignment = dict(zip(priority, STANDARD_ARRAY))

    table = Table(title="Standard Array Assignment", show_header=True)
    table.add_column("Ability", style="bold cyan")
    table.add_column("Score", justify="right")
    for ab in ABILITY_ORDER:
        table.add_row(ab, str(default_assignment[ab]))
    console.print(table)

    answer = console.input(
        "[dim]Accept this stat assignment? (Y/n): [/dim]"
    ).strip().lower()
    if answer in ("", "y", "yes"):
        return default_assignment

    # Custom assignment
    console.print(f"[dim]Enter scores for each ability (pool: {STANDARD_ARRAY}).[/dim]")
    remaining = list(STANDARD_ARRAY)
    assignment: dict[str, int] = {}
    for ab in ABILITY_ORDER:
        while True:
            choices = ", ".join(str(v) for v in sorted(remaining, reverse=True))
            raw = console.input(f"  {ab} [{choices}]: ").strip()
            try:
                val = int(raw)
            except ValueError:
                console.print("[red]  Enter a number.[/red]")
                continue
            if val not in remaining:
                console.print(f"[red]  {val} not available. Remaining: {choices}[/red]")
                continue
            remaining.remove(val)
            assignment[ab] = val
            break
    return assignment


def _create_one_character(n: int, existing_ids: set[str]) -> Character:
    """Walk the wizard for a single character. Returns a fully constructed Character."""
    console.print(f"\n[bold cyan]--- Character {n} ---[/bold cyan]")

    name = ""
    while not name:
        name = console.input("[bold]Name[/bold]: ").strip()

    race = _pick("Race", RACES, default="Human")
    class_name = _pick("Class", sorted(CLASS_TEMPLATES.keys()), default="Fighter")
    background = _pick("Background", sorted(BACKGROUNDS.keys()), default="Folk Hero")
    alignment = _pick("Alignment", ALIGNMENTS, default="Neutral Good")

    # Personality (all optional — press Enter to skip)
    console.print("[dim]Describe your character's personality (press Enter to skip any):[/dim]")
    personality_traits = console.input("  Personality traits: ").strip() or None
    ideals = console.input("  Ideals: ").strip() or None
    bonds = console.input("  Bonds: ").strip() or None
    flaws = console.input("  Flaws: ").strip() or None

    template = CLASS_TEMPLATES[class_name]
    stat_map = _assign_stats(class_name)

    ability_scores = AbilityScores(**stat_map)
    con_mod = ability_scores.modifier("CON")
    die_sides = int(template["hit_die"][1:])

    # Level 1: max HP = hit die max + CON mod (minimum 1)
    max_hp = max(1, die_sides + con_mod)

    # AC depends on armor type
    armor_data = template["starting_armor"]
    armor: Armor | None = None
    ac = 10 + ability_scores.modifier("DEX")  # unarmored default

    if armor_data:
        armor = Armor(**armor_data)
        if armor.armor_type == "light":
            ac = armor.base_ac + ability_scores.modifier("DEX")
        elif armor.armor_type == "medium":
            ac = armor.base_ac + min(2, ability_scores.modifier("DEX"))
        else:  # heavy
            ac = armor.base_ac
    elif class_name == "Monk":
        # Unarmored Defense: 10 + DEX + WIS
        ac = 10 + ability_scores.modifier("DEX") + ability_scores.modifier("WIS")
    elif class_name == "Barbarian":
        # Unarmored Defense: 10 + DEX + CON
        ac = 10 + ability_scores.modifier("DEX") + con_mod

    # Starting weapons
    weapons = [
        Weapon(
            name=w["name"],
            damage_dice=w["damage_dice"],
            damage_type=w["damage_type"],
            properties=w.get("properties", []),
            range_normal=w.get("range_normal"),
            range_long=w.get("range_long"),
        )
        for w in template["starting_weapons"]
    ]

    # Spell slots at level 1
    spell_slots = get_spell_slots_for_level(class_name, 1)

    # Background skill proficiencies (automatic)
    bg_data = BACKGROUNDS[background]
    bg_skills = list(bg_data["skill_proficiencies"])
    console.print(f"[dim]Background ({background}) grants: {', '.join(bg_skills)}[/dim]")

    # Choose 2 class skills (excluding background skills already granted)
    skill_options = [s for s in template["skill_options"] if s not in bg_skills]
    console.print(f"[dim]Choose 2 skill proficiencies from: {', '.join(skill_options)}[/dim]")
    skills: list[str] = list(bg_skills)
    opts_lower = [s.lower() for s in skill_options]
    while len(skills) < len(bg_skills) + 2:
        raw = console.input(f"  Skill {len(skills) - len(bg_skills) + 1}: ").strip()
        if raw.lower() in opts_lower:
            picked = skill_options[opts_lower.index(raw.lower())]
            if picked not in skills:
                skills.append(picked)
            else:
                console.print("[red]  Already chosen.[/red]")
        else:
            console.print(f"[red]  Not a valid option.[/red]")

    # Build unique ID
    char_id = _slugify(name)
    if char_id in existing_ids:
        char_id = f"{char_id}_{n}"

    char = Character(
        id=char_id,
        name=name,
        race=race,
        class_name=class_name,
        level=1,
        xp=0,
        ability_scores=ability_scores,
        hp=max_hp,
        max_hp=max_hp,
        ac=ac,
        speed=30,
        proficiency_bonus=proficiency_bonus_for_level(1),
        skill_proficiencies=skills,
        weapon_proficiencies=template["weapon_proficiencies"],
        armor_proficiencies=template["armor_proficiencies"],
        saving_throw_proficiencies=template["saves"],
        spell_slots=spell_slots,
        max_spell_slots=dict(spell_slots),
        spellcasting_ability=template["spellcasting_ability"],
        known_spells=list(template["starting_spells"]),
        hit_dice_remaining=1,
        hit_die_type=template["hit_die"],
        class_resources=dict(template["class_resources"]),
        weapons=weapons,
        armor=armor,
        background=background,
        alignment=alignment,
        personality_traits=personality_traits,
        ideals=ideals,
        bonds=bonds,
        flaws=flaws,
        is_player=True,
    )

    console.print(f"\n[green]  ✓ {name} the {race} {class_name} ({background}) — HP {max_hp}, AC {ac}[/green]")
    return char


def create_characters(campaign=None) -> list[Character]:
    """Interactive wizard: create 1 or 2 player characters. Returns list[Character]."""
    console.print("\n[bold cyan]═══ Character Creation ═══[/bold cyan]\n")

    while True:
        raw = console.input("[bold]How many characters?[/bold] [1/2]: ").strip()
        if raw in ("1", "2", ""):
            count = int(raw) if raw else 2
            break
        console.print("[red]  Enter 1 or 2.[/red]")

    existing_ids: set[str] = set()
    characters: list[Character] = []
    for i in range(1, count + 1):
        char = _create_one_character(i, existing_ids)
        existing_ids.add(char.id)
        characters.append(char)

    console.print("\n[bold green]Character creation complete![/bold green]")
    return characters
