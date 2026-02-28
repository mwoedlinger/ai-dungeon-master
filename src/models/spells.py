"""Spell data models."""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class SpellResolution(str, Enum):
    ATTACK_ROLL = "attack_roll"
    SAVE_DAMAGE = "save_damage"
    SAVE_EFFECT = "save_effect"
    HEALING = "healing"
    BUFF = "buff"
    NARRATIVE = "narrative"


class SpellData(BaseModel):
    name: str
    level: int  # 0 for cantrips
    resolution: SpellResolution
    casting_time: str  # "action", "bonus_action", "reaction"
    concentration: bool = False
    damage_dice: str | None = None
    damage_type: str | None = None
    save_ability: str | None = None
    healing_dice: str | None = None
    buff_effect: str | None = None
    duration_rounds: int | None = None
    upcast_bonus: str | None = None  # "+1d6 per level" or "+1 target per level"
    description: str
    aoe: bool = False
    condition_effect: str | None = None  # condition applied by SAVE_EFFECT spells
