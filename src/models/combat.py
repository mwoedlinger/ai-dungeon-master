"""Combat state models."""
from __future__ import annotations

from pydantic import BaseModel


class DiceResult(BaseModel):
    expression: str
    individual_rolls: list[int]
    modifier: int
    total: int
    advantage: bool = False
    disadvantage: bool = False
    kept_roll: int | None = None  # d20 value used (for crit detection)


class CheckResult(BaseModel):
    roll: DiceResult
    modifier: int
    total: int
    dc: int
    success: bool
    nat_20: bool = False
    nat_1: bool = False


class AttackResult(BaseModel):
    roll: DiceResult
    attack_bonus: int
    total_attack: int
    target_ac: int
    hits: bool
    is_crit: bool
    is_nat1: bool
    damage: int | None = None
    damage_type: str | None = None


class Combatant(BaseModel):
    character_id: str
    initiative: int
    has_action: bool = True
    has_bonus_action: bool = True
    has_reaction: bool = True
    movement_remaining: int
    condition_durations: dict[str, int | None] = {}  # condition -> rounds remaining (None = indefinite)


class CombatState(BaseModel):
    active: bool = False
    round: int = 0
    turn_order: list[str] = []  # character ids in initiative order
    current_turn_index: int = 0
    combatants: dict[str, Combatant] = {}

    @property
    def current_combatant_id(self) -> str:
        if not self.turn_order:
            return ""
        return self.turn_order[self.current_turn_index]

    def consume_action(self, character_id: str) -> bool:
        """Returns False if no action available."""
        c = self.combatants.get(character_id)
        if not c or not c.has_action:
            return False
        c.has_action = False
        return True

    def consume_bonus_action(self, character_id: str) -> bool:
        c = self.combatants.get(character_id)
        if not c or not c.has_bonus_action:
            return False
        c.has_bonus_action = False
        return True
