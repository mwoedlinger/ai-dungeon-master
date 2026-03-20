"""Dungeon Weaver — entry point."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure src is on the path when running as a script
sys.path.insert(0, str(Path(__file__).parent))

from src.campaign.loader import load_campaign, load_srd_data, validate_campaign
from src.dm.dungeon_master import DungeonMaster
from src.engine.game_state import GameState
from src.interface.cli import console
from src.interface.session import SessionManager
from src.log.event_log import EventLog
from src.models.character import Character
from src.models.world import Quest, WorldState


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dungeon Weaver")
    p.add_argument("--campaign", default="campaigns/shattered_crown",
                   help="Path to campaign (JSON file or YAML directory)")
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
    p.add_argument("--validate-campaign", action="store_true",
                   help="Validate campaign cross-references and exit")
    p.add_argument("--debug", action="store_true",
                   help="Print tool calls, inputs, and results in real-time alongside narrative")
    p.add_argument("--verbose", action="store_true",
                   help="Enable verbose logging (compression events, token usage, context management)")
    return p.parse_args()


def _load_characters_from_file(path: Path) -> tuple[dict[str, Character], list[str]]:
    """Load characters from a JSON file. Returns (characters_dict, pc_ids)."""
    data = json.loads(path.read_text())
    characters: dict[str, Character] = {}
    pc_ids: list[str] = []
    for char_data in data.get("characters", []):
        char = Character.model_validate(char_data)
        characters[char.id] = char
        if char.is_player:
            pc_ids.append(char.id)
    return characters, pc_ids


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
            sys.exit(1)
        characters, pc_ids = _load_characters_from_file(chars_path)
        console.print(f"[dim]Loaded {len(pc_ids)} character(s) from {chars_path}[/dim]")
    else:
        # Default: load from default_characters.json
        default_path = Path("campaigns/default_characters.json")
        if not default_path.exists():
            console.print("[red]Default characters file not found: campaigns/default_characters.json[/red]")
            console.print("[yellow]Use 'create' to make new characters instead.[/yellow]")
            sys.exit(1)
        characters, pc_ids = _load_characters_from_file(default_path)
        console.print(f"[dim]Loaded default characters: {', '.join(c.name for c in characters.values())}[/dim]")

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
                rewards=h.rewards,
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


_AUTH_HELP = {
    "anthropic": (
        "ANTHROPIC_API_KEY",
        "https://console.anthropic.com/settings/keys",
        'export ANTHROPIC_API_KEY="sk-ant-..."',
    ),
    "gemini": (
        "GOOGLE_API_KEY",
        "https://aistudio.google.com/apikey",
        'export GOOGLE_API_KEY="..."',
    ),
    "deepseek": (
        "DEEPSEEK_API_KEY",
        "https://platform.deepseek.com/api_keys",
        'export DEEPSEEK_API_KEY="..."',
    ),
    "ollama": (
        None,
        None,
        "Ensure Ollama is running: ollama serve",
    ),
}


def _handle_auth_error(error: Exception, provider: str) -> None:
    """Print a user-friendly message for authentication errors."""
    env_var, url, example = _AUTH_HELP.get(provider, (None, None, None))
    console.print(f"\n[bold red]Authentication error for provider '{provider}':[/bold red]")
    console.print(f"  {error}\n")
    if env_var:
        console.print(f"[yellow]Set your API key as an environment variable:[/yellow]")
        console.print(f"  [bold]{example}[/bold]\n")
        console.print(f"[dim]Get your key at: {url}[/dim]")
        console.print(f"[dim]Or add it to your shell profile (~/.zshrc or ~/.bashrc) to persist.[/dim]\n")
    elif example:
        console.print(f"[yellow]{example}[/yellow]\n")
    sys.exit(1)


def _setup_logging(
    debug: bool = False,
    verbose: bool = False,
    log_dir: str = "logs",
) -> Path | None:
    """Configure structured logging based on CLI flags.

    When *debug* is True, a debug log file is written to *log_dir*/ with the
    full DEBUG stream (including all LLM I/O).  The console only shows WARNING
    unless *verbose* (→ INFO) or *debug* (→ DEBUG) is set.

    Returns the path to the debug log file, or None.
    """
    console_level = logging.WARNING
    if debug:
        console_level = logging.DEBUG
    elif verbose:
        console_level = logging.INFO

    logging.basicConfig(
        level=console_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    # Suppress noisy third-party loggers even in debug mode
    for noisy in ("httpx", "httpcore", "urllib3", "google", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Always write a debug log file when --debug is on
    debug_log_path = None
    if debug:
        from datetime import datetime
        log_dir_path = Path(log_dir)
        log_dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_log_path = log_dir_path / f"debug_{timestamp}.log"
        file_handler = logging.FileHandler(debug_log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logging.getLogger().addHandler(file_handler)
        # Ensure root logger level captures DEBUG for the file handler
        logging.getLogger().setLevel(logging.DEBUG)

    return debug_log_path


def _debug_tool_callback(tool_name: str, inputs: dict, result: dict) -> None:
    """Print tool calls in real-time for --debug mode."""
    success = result.get("success", True)
    status = "[green]OK[/green]" if success else f"[red]FAIL: {result.get('error', '?')}[/red]"

    # Compact input display
    input_parts = []
    for k, v in list(inputs.items())[:4]:
        val = str(v)
        if len(val) > 40:
            val = val[:37] + "..."
        input_parts.append(f"{k}={val}")
    input_str = ", ".join(input_parts)

    console.print(f"  [dim]⚙ {tool_name}({input_str}) → {status}[/dim]")


def main() -> None:
    args = parse_args()

    # Set up logging based on flags
    debug_log_path = _setup_logging(debug=args.debug, verbose=args.verbose)
    if debug_log_path:
        console.print(f"[dim]Debug log: {debug_log_path}[/dim]")

    # Load SRD data
    load_srd_data()
    console.print("[dim]SRD data loaded.[/dim]")

    # Load campaign (try directory first, then .json fallback)
    campaign_path = Path(args.campaign)
    if not campaign_path.exists():
        # If given without extension, try adding .json
        json_fallback = campaign_path.with_suffix(".json")
        if json_fallback.exists():
            campaign_path = json_fallback
        else:
            console.print(f"[red]Campaign not found: {campaign_path}[/red]")
            sys.exit(1)

    campaign = load_campaign(campaign_path)
    console.print(f"[dim]Campaign loaded: {campaign.title}[/dim]")

    # Validate-only mode
    if args.validate_campaign:
        errors = validate_campaign(campaign)
        if errors:
            console.print("[red]Campaign validation failed:[/red]")
            for err in errors:
                console.print(f"  [red]• {err}[/red]")
            sys.exit(1)
        else:
            console.print("[green]Campaign validation passed — all references OK.[/green]")
            sys.exit(0)

    # Load or create game state
    game_state = load_game_state(args, campaign)
    game_state.campaign = campaign

    # Set up persistent event log alongside the save file
    save_path = Path(args.autosave)
    event_log_path = save_path.with_suffix(".events.jsonl")
    event_log = EventLog(game_state, persist_path=event_log_path)

    if args.debug or args.verbose:
        console.print(f"[dim]Event log: {event_log_path}[/dim]")

    # Set up DM
    try:
        dm = DungeonMaster(
            game_state=game_state,
            campaign=campaign,
            event_log=event_log,
            provider=args.provider,
            model=args.model,
            save_path=args.autosave,
            debug=args.debug,
        )
    except Exception as e:
        _handle_auth_error(e, args.provider)
        raise

    # Wire up debug tool callback
    if args.debug:
        dm._on_tool_call = _debug_tool_callback

    # Player names from characters
    player_names = [
        game_state.characters[cid].name
        for cid in game_state.player_character_ids
        if cid in game_state.characters
    ]

    # Run session
    session = SessionManager(dm, game_state, event_log, player_names, save_path=args.autosave)
    try:
        session.run()
    except TypeError as e:
        if "authentication" in str(e).lower() or "api_key" in str(e).lower():
            _handle_auth_error(e, args.provider)
        else:
            raise
    finally:
        # Print session token stats
        stats = dm.token_stats.summary()
        if stats["api_calls"] > 0:
            console.print(f"\n[dim]Session stats: {stats['api_calls']} API calls, "
                          f"{stats['total_tokens']:,} tokens "
                          f"(in: {stats['input_tokens']:,}, out: {stats['output_tokens']:,}), "
                          f"est. cost: ${stats['estimated_cost_usd']:.4f}[/dim]")
        event_log.close()


if __name__ == "__main__":
    main()
