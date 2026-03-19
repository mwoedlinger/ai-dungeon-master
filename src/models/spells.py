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
    AUTO_DAMAGE = "auto_damage"
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
    save_negates: bool = False  # True = 0 damage on successful save (Disintegrate)
    healing_dice: str | None = None
    flat_healing: int | None = None  # Fixed healing amount (Heal: 70)
    buff_effect: str | None = None
    duration_rounds: int | None = None
    upcast_bonus: str | None = None  # "+1d6 per level" or "+1 target per level"
    upcast_pattern: str = "damage"  # "damage", "targets", "duration", "flat_healing"
    cantrip_scaling: dict[int, str] | None = None  # {1: "1d10", 5: "2d10", ...}
    description: str
    aoe: bool = False
    condition_effect: str | None = None  # condition applied by SAVE_EFFECT spells
