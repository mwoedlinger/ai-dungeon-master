"""Pydantic response models for the web API."""
from __future__ import annotations

from pydantic import BaseModel


class GameStateSnapshot(BaseModel):
    """Serializable snapshot pushed to the frontend via state_update."""
    characters: list[dict]
    combat: dict | None
    world: dict
    journal: dict
    mode: str  # "exploration" | "combat"
    current_turn: dict | None = None


class SessionNewRequest(BaseModel):
    characters_json: str | None = None
    characters: list[dict] | None = None
    save_path: str = "saves/autosave.json"


class SessionLoadRequest(BaseModel):
    save_path: str
