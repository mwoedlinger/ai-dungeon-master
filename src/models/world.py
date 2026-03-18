"""World state models."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel
from src.models.character import Character


class TreasureItem(BaseModel):
    """A pre-placed item at a location, discoverable by players."""
    name: str
    description: str = ""
    item_type: str = "mundane"  # "mundane", "weapon", "armor", "potion", "scroll", "wondrous", "ring", "staff"
    rarity: str = "common"  # "common", "uncommon", "rare", "very_rare", "legendary"
    bonus: int = 0  # +1/+2/+3 for weapons/armor
    weight: float = 0.0
    value_gp: int = 0
    requires_attunement: bool = False
    properties: dict[str, Any] = {}
    discovery: str = ""  # how it can be found: "hidden behind altar, DC 15 Investigation", "chest in main hall"
    found: bool = False  # set to True once players discover it


class Location(BaseModel):
    id: str
    name: str
    description: str
    parent: str | None = None
    connected_to: list[str] = []
    treasure: list[TreasureItem] = []


class QuestReward(BaseModel):
    xp: int = 0
    gold: int = 0
    items: list[str] = []  # item names to distribute


class Quest(BaseModel):
    id: str
    title: str
    description: str
    status: Literal["active", "completed", "failed"]
    objectives: list[str] = []
    completed_objectives: list[str] = []
    rewards: QuestReward | None = None


class TimeState(BaseModel):
    """In-game calendar tracking."""
    day: int = 1  # day of the campaign (1-indexed)
    hour: int = 8  # 0-23, starts at 8am
    minute: int = 0

    @property
    def time_of_day(self) -> str:
        if 6 <= self.hour < 12:
            return "morning"
        elif 12 <= self.hour < 17:
            return "afternoon"
        elif 17 <= self.hour < 21:
            return "evening"
        else:
            return "night"

    @property
    def is_daytime(self) -> bool:
        return 6 <= self.hour < 21

    def formatted(self) -> str:
        return f"Day {self.day}, {self.hour:02d}:{self.minute:02d} ({self.time_of_day})"


class WorldState(BaseModel):
    current_location_id: str
    locations: dict[str, Location] = {}
    active_npcs: dict[str, Character] = {}
    quests: list[Quest] = []
    world_notes: str = ""
    time: TimeState = TimeState()
