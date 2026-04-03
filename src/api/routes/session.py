"""Session lifecycle REST endpoints."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from src.api.events import EventBridge
from src.api.game_server import GameSession
from src.api.schemas import SessionLoadRequest, SessionNewRequest
from src.dm.dungeon_master import DungeonMaster
from src.engine.game_state import GameState
from src.log.event_log import EventLog
from src.models.character import Character
from src.models.world import Quest, WorldState

logger = logging.getLogger(__name__)

router = APIRouter()


def _load_characters_from_data(data: dict) -> tuple[dict[str, Character], list[str]]:
    characters: dict[str, Character] = {}
    pc_ids: list[str] = []
    for char_data in data.get("characters", []):
        char = Character.model_validate(char_data)
        characters[char.id] = char
        if char.is_player:
            pc_ids.append(char.id)
    return characters, pc_ids


def _build_game_state(
    characters: dict[str, Character],
    pc_ids: list[str],
    campaign,
) -> GameState:
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
            for h in campaign.plot_hooks[:2]
        ],
    )
    return GameState(
        player_character_ids=pc_ids,
        characters=characters,
        world=world,
        campaign=campaign,
    )


@router.post("/session/new")
async def new_session(req: SessionNewRequest, request: Request) -> dict:
    """Create a new game session."""
    campaign = request.app.state.campaign
    provider = request.app.state.provider
    model = request.app.state.model

    # Load characters
    if req.characters:
        characters: dict[str, Character] = {}
        pc_ids: list[str] = []
        for c in req.characters:
            char = Character.model_validate(c)
            characters[char.id] = char
            if char.is_player:
                pc_ids.append(char.id)
    elif req.characters_json:
        char_path = Path(req.characters_json)
        if not char_path.exists():
            raise HTTPException(404, f"Characters file not found: {char_path}")
        data = json.loads(char_path.read_text())
        characters, pc_ids = _load_characters_from_data(data)
    else:
        # Try default characters
        for default in ["campaigns/default_characters.json", "campaigns/test_characters.json"]:
            p = Path(default)
            if p.exists():
                data = json.loads(p.read_text())
                characters, pc_ids = _load_characters_from_data(data)
                break
        else:
            raise HTTPException(400, "No characters provided and no default file found.")

    game_state = _build_game_state(characters, pc_ids, campaign)
    game_state.campaign = campaign

    save_path = Path(req.save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    event_log_path = save_path.with_suffix(".events.jsonl")
    event_log = EventLog(game_state, persist_path=event_log_path)

    dm = DungeonMaster(
        game_state=game_state,
        campaign=campaign,
        event_log=event_log,
        provider=provider,
        model=model,
        save_path=str(save_path),
        debug=getattr(request.app.state, "debug", False),
    )

    session = GameSession(
        dm=dm,
        game_state=game_state,
        event_log=event_log,
        event_bridge=EventBridge(event_log),
        save_path=str(save_path),
    )
    request.app.state.session = session

    logger.info("New session created with %d characters", len(pc_ids))
    return {
        "status": "ok",
        "characters": [c.model_dump() for c in game_state.player_characters],
    }


@router.post("/session/load")
async def load_session(req: SessionLoadRequest, request: Request) -> dict:
    """Load a game from a save file."""
    campaign = request.app.state.campaign
    provider = request.app.state.provider
    model = request.app.state.model

    save_path = Path(req.save_path)
    if not save_path.exists():
        raise HTTPException(404, f"Save file not found: {save_path}")

    game_state = GameState.load(str(save_path), campaign=campaign)
    game_state.campaign = campaign

    # Inject campaign locations
    for loc_id, loc in campaign.locations.items():
        if loc_id not in game_state.world.locations:
            game_state.world.locations[loc_id] = loc

    event_log_path = save_path.with_suffix(".events.jsonl")
    event_log = EventLog(game_state, persist_path=event_log_path)

    dm = DungeonMaster(
        game_state=game_state,
        campaign=campaign,
        event_log=event_log,
        provider=provider,
        model=model,
        save_path=str(save_path),
        debug=getattr(request.app.state, "debug", False),
    )

    session = GameSession(
        dm=dm,
        game_state=game_state,
        event_log=event_log,
        event_bridge=EventBridge(event_log),
        save_path=str(save_path),
    )
    # Mark opening as done (loaded game)
    session._opening_done = True
    request.app.state.session = session

    logger.info("Session loaded from %s", save_path)
    return {
        "status": "ok",
        "characters": [c.model_dump() for c in game_state.player_characters],
    }


@router.delete("/session")
async def end_session(request: Request) -> dict:
    """End the current session."""
    session: GameSession | None = request.app.state.session
    if session:
        session.event_log.close()
        request.app.state.session = None
    return {"status": "ok"}
