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


class LegendaryAction(BaseModel):
    name: str
    description: str
    cost: int = 1  # how many legendary action uses this consumes


class LairAction(BaseModel):
    description: str
    save_dc: int | None = None
    save_ability: str | None = None
    damage_dice: str | None = None
    damage_type: str | None = None
    condition_effect: str | None = None


class Monster(Character):
    is_player: bool = False
    challenge_rating: float = 0
    xp_value: int = 0
    actions: list[MonsterAction] = []
    special_traits: list[str] = []
    damage_resistances: list[str] = []
    damage_immunities: list[str] = []
    condition_immunities: list[str] = []
    # Boss monster mechanics
    legendary_actions: list[LegendaryAction] = []
    legendary_actions_per_round: int = 0  # 0 = no legendary actions
    legendary_actions_remaining: int = 0
    legendary_resistances: int = 0  # auto-succeed saving throws (per day)
    legendary_resistances_remaining: int = 0
    lair_actions: list[LairAction] = []
    has_lair: bool = False
