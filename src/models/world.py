"""World state models."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel
from src.models.character import Character


class Location(BaseModel):
    id: str
    name: str
    description: str
    parent: str | None = None
    connected_to: list[str] = []


class Quest(BaseModel):
    id: str
    title: str
    description: str
    status: Literal["active", "completed", "failed"]
    objectives: list[str] = []
    completed_objectives: list[str] = []


class WorldState(BaseModel):
    current_location_id: str
    locations: dict[str, Location] = {}
    active_npcs: dict[str, Character] = {}
    quests: list[Quest] = []
    world_notes: str = ""
