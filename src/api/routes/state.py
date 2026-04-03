"""Read-only state query endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.api.game_server import GameSession

router = APIRouter()


def _require_session(request: Request) -> GameSession:
    session: GameSession | None = request.app.state.session
    if session is None:
        raise HTTPException(400, "No active session.")
    return session


@router.get("/state")
async def get_state(request: Request) -> dict:
    session = _require_session(request)
    return session.snapshot().model_dump()


@router.get("/characters")
async def get_characters(request: Request) -> list[dict]:
    session = _require_session(request)
    return [c.model_dump() for c in session.game_state.player_characters]


@router.get("/characters/{char_id}")
async def get_character(char_id: str, request: Request) -> dict:
    session = _require_session(request)
    try:
        return session.game_state.get_character_sheet(char_id)
    except KeyError:
        raise HTTPException(404, f"Character not found: {char_id}")


@router.get("/characters/{char_id}/inventory")
async def get_inventory(char_id: str, request: Request) -> dict:
    session = _require_session(request)
    try:
        char = session.game_state.get_character(char_id)
    except KeyError:
        raise HTTPException(404, f"Character not found: {char_id}")
    return {
        "weapons": [w.model_dump() for w in char.weapons],
        "armor": char.armor.model_dump() if char.armor else None,
        "shield": char.shield,
        "attuned_items": [m.model_dump() for m in char.attuned_items],
        "inventory": [i.model_dump() for i in char.inventory],
        "gold": char.gold,
    }


@router.get("/combat")
async def get_combat(request: Request) -> dict | None:
    session = _require_session(request)
    combat = session.game_state.combat
    if not combat.active:
        return None
    return combat.model_dump()


@router.get("/world")
async def get_world(request: Request) -> dict:
    session = _require_session(request)
    return session.game_state.world.model_dump()


@router.get("/world/location")
async def get_location(request: Request) -> dict | None:
    session = _require_session(request)
    world = session.game_state.world
    loc = world.locations.get(world.current_location_id)
    if loc is None:
        return None
    return loc.model_dump()


@router.get("/journal")
async def get_journal(request: Request) -> dict:
    session = _require_session(request)
    return session.game_state.journal.model_dump()
