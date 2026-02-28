"""AI Dungeon Master — entry point."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure src is on the path when running as a script
sys.path.insert(0, str(Path(__file__).parent))

from src.campaign.loader import load_campaign, load_srd_data
from src.dm.dungeon_master import DungeonMaster
from src.engine.game_state import GameState
from src.interface.cli import console
from src.interface.session import SessionManager
from src.log.event_log import EventLog
from src.models.character import Character
from src.models.combat import CombatState
from src.models.world import Location, Quest, WorldState


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Dungeon Master")
    p.add_argument("--campaign", default="campaigns/shattered_crown.json",
                   help="Path to campaign JSON file")
    p.add_argument("--save", default=None, help="Path to save file (load existing)")
    p.add_argument("--new", action="store_true", help="Start a new game (ignore --save)")
    p.add_argument("--provider", default="anthropic",
                   choices=["anthropic", "gemini", "ollama", "deepseek"],
                   help="LLM provider (default: anthropic)")
    p.add_argument("--model", default=None,
                   help="Model name override (default per provider: "
                        "anthropic=claude-sonnet-4-6, gemini=gemini-2.0-flash, "
                        "ollama=llama3.2, deepseek=deepseek-chat). "
                        "For DeepSeek thinking mode use: deepseek-reasoner")
    p.add_argument("--characters", default="campaigns/test_characters.json",
                   help="Path to starting characters JSON (for new games)")
    p.add_argument("--autosave", default="saves/autosave.json",
                   help="Path for auto-save file")
    return p.parse_args()


def load_game_state(
    args: argparse.Namespace,
    campaign,
) -> GameState:
    """Load from save file or create a new game state."""
    save_path = args.save or args.autosave

    if not args.new and save_path and Path(save_path).exists():
        console.print(f"[dim]Loading save: {save_path}[/dim]")
        gs = GameState.load(save_path, campaign=campaign)
        # Inject locations from campaign into world state
        for loc_id, loc in campaign.locations.items():
            if loc_id not in gs.world.locations:
                gs.world.locations[loc_id] = loc
        return gs

    # New game — choose character setup method
    from rich.prompt import Prompt
    choice = Prompt.ask(
        "\nCharacter setup",
        choices=["create", "file", "default"],
        default="create",
    )

    if choice == "create":
        from src.interface.character_creation import create_characters
        char_list = create_characters(campaign)
        characters = {c.id: c for c in char_list}
        pc_ids = [c.id for c in char_list]
    elif choice == "file":
        chars_path = Path(args.characters)
        if not chars_path.exists():
            console.print(f"[red]Characters file not found: {chars_path}[/red]")
            console.print("[yellow]Creating default characters...[/yellow]")
            return _create_default_game_state(campaign)
        data = json.loads(chars_path.read_text())
        characters = {}
        pc_ids = []
        for char_data in data.get("characters", []):
            char = Character.model_validate(char_data)
            characters[char.id] = char
            if char.is_player:
                pc_ids.append(char.id)
    else:
        return _create_default_game_state(campaign)

    # Build world state from campaign
    starting_loc = campaign.starting_location_id or next(iter(campaign.locations))
    world = WorldState(
        current_location_id=starting_loc,
        locations=dict(campaign.locations),
        quests=[
            Quest(
                id=h.id,
                title=h.title,
                description=h.description,
                status="active",
                objectives=[h.description],
            )
            for h in campaign.plot_hooks[:2]  # Start with first 2 plot hooks as quests
        ],
    )

    gs = GameState(
        player_character_ids=pc_ids,
        characters=characters,
        world=world,
        campaign=campaign,
    )
    return gs


def _create_default_game_state(campaign) -> GameState:
    """Fallback minimal game state."""
    from src.models.character import AbilityScores, Armor, Weapon

    fighter = Character(
        id="aldric",
        name="Aldric Stonemantle",
        race="Human",
        class_name="Fighter",
        level=3,
        xp=900,
        ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
        hp=28,
        max_hp=28,
        ac=16,
        proficiency_bonus=2,
        skill_proficiencies=["Athletics", "Perception"],
        weapon_proficiencies=["martial", "simple"],
        armor_proficiencies=["light", "medium", "heavy", "shields"],
        saving_throw_proficiencies=["STR", "CON"],
        hit_dice_remaining=3,
        hit_die_type="d10",
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
    )
    wizard = Character(
        id="zara",
        name="Zara Moonwhisper",
        race="Half-Elf",
        class_name="Wizard",
        level=3,
        xp=900,
        ability_scores=AbilityScores(STR=8, DEX=14, CON=12, INT=16, WIS=12, CHA=14),
        hp=19,
        max_hp=19,
        ac=13,
        proficiency_bonus=2,
        skill_proficiencies=["Arcana", "History", "Investigation"],
        weapon_proficiencies=["simple"],
        armor_proficiencies=["light"],
        saving_throw_proficiencies=["INT", "WIS"],
        spell_slots={1: 4, 2: 2},
        max_spell_slots={1: 4, 2: 2},
        spellcasting_ability="INT",
        known_spells=["Fire Bolt", "Magic Missile", "Fireball", "Shield", "Mage Armor"],
        hit_dice_remaining=3,
        hit_die_type="d6",
        weapons=[],
    )

    starting_loc = campaign.starting_location_id or next(iter(campaign.locations))
    world = WorldState(
        current_location_id=starting_loc,
        locations=dict(campaign.locations),
    )
    return GameState(
        player_character_ids=["aldric", "zara"],
        characters={"aldric": fighter, "zara": wizard},
        world=world,
        campaign=campaign,
    )


def main() -> None:
    args = parse_args()

    # Load SRD data
    load_srd_data()
    console.print("[dim]SRD data loaded.[/dim]")

    # Load campaign
    campaign_path = Path(args.campaign)
    if not campaign_path.exists():
        console.print(f"[red]Campaign file not found: {campaign_path}[/red]")
        sys.exit(1)

    campaign = load_campaign(campaign_path)
    console.print(f"[dim]Campaign loaded: {campaign.title}[/dim]")

    # Load or create game state
    game_state = load_game_state(args, campaign)
    game_state.campaign = campaign

    # Set up event log
    event_log = EventLog(game_state)

    # Set up DM
    dm = DungeonMaster(
        game_state=game_state,
        campaign=campaign,
        event_log=event_log,
        provider=args.provider,
        model=args.model,
        save_path=args.autosave,
    )

    # Player names from characters
    player_names = [
        game_state.characters[cid].name
        for cid in game_state.player_character_ids
        if cid in game_state.characters
    ]

    # Run session
    session = SessionManager(dm, game_state, event_log, player_names)
    session.run()


if __name__ == "__main__":
    main()
