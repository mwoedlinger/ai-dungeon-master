"""Character data models."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel


class AbilityScores(BaseModel):
    STR: int
    DEX: int
    CON: int
    INT: int
    WIS: int
    CHA: int

    def modifier(self, ability: str) -> int:
        return (getattr(self, ability) - 10) // 2


class DeathSaves(BaseModel):
    successes: int = 0
    failures: int = 0


class Item(BaseModel):
    name: str
    description: str = ""
    quantity: int = 1
    weight: float = 0.0
    properties: dict[str, Any] = {}


class Weapon(BaseModel):
    name: str
    damage_dice: str
    damage_type: str
    properties: list[str] = []
    range_normal: int | None = None
    range_long: int | None = None
    attack_bonus_override: int | None = None


class Armor(BaseModel):
    name: str
    base_ac: int
    armor_type: str  # light, medium, heavy, shield
    stealth_disadvantage: bool = False
    strength_requirement: int | None = None


class Character(BaseModel):
    id: str
    name: str
    race: str
    class_name: str
    subclass: str | None = None
    level: int = 1
    xp: int = 0

    ability_scores: AbilityScores
    hp: int
    max_hp: int
    temp_hp: int = 0
    ac: int
    speed: int = 30

    proficiency_bonus: int
    skill_proficiencies: list[str] = []
    weapon_proficiencies: list[str] = []
    armor_proficiencies: list[str] = []
    saving_throw_proficiencies: list[str] = []

    spell_slots: dict[int, int] = {}
    max_spell_slots: dict[int, int] = {}
    spellcasting_ability: str | None = None
    known_spells: list[str] = []
    hit_dice_remaining: int = 0
    hit_die_type: str = "d8"
    class_resources: dict[str, int] = {}

    weapons: list[Weapon] = []
    armor: Armor | None = None
    shield: bool = False
    inventory: list[Item] = []

    conditions: list[str] = []
    concentration: str | None = None
    death_saves: DeathSaves = DeathSaves()
    is_player: bool = True

    @property
    def spell_save_dc(self) -> int | None:
        if self.spellcasting_ability:
            return 8 + self.proficiency_bonus + self.ability_scores.modifier(self.spellcasting_ability)
        return None
