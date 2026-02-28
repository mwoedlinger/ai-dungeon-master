"""Monster data models."""
from __future__ import annotations

from pydantic import BaseModel
from src.models.character import Character


class MonsterAction(BaseModel):
    name: str
    description: str
    action_type: str  # action, bonus_action, reaction
    attack_bonus: int | None = None
    damage_dice: str | None = None
    damage_type: str | None = None
    save_dc: int | None = None
    save_ability: str | None = None
    recharge: str | None = None
    available: bool = True


class Monster(Character):
    is_player: bool = False
    challenge_rating: float = 0
    xp_value: int = 0
    actions: list[MonsterAction] = []
    special_traits: list[str] = []
    damage_resistances: list[str] = []
    damage_immunities: list[str] = []
    condition_immunities: list[str] = []
