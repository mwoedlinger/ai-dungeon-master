"""Dice rolling engine. All randomness in the game lives here."""
from __future__ import annotations

import random
import re

from src.models.combat import DiceResult


def roll_dice(
    expr: str,
    advantage: bool = False,
    disadvantage: bool = False,
) -> DiceResult:
    """Parse and evaluate dice expressions.

    Supports: NdM, NdM+X, NdM-X, dM, NdMkhK (keep highest K).
    Advantage/disadvantage applies to the d20 roll only.
    """
    expr = expr.strip().lower()

    # Normalize: advantage + disadvantage cancel out
    if advantage and disadvantage:
        advantage = False
        disadvantage = False

    # Parse keep-highest notation: e.g. "4d6kh3"
    kh_match = re.fullmatch(r"(\d*)d(\d+)kh(\d+)", expr)
    if kh_match:
        n = int(kh_match.group(1)) if kh_match.group(1) else 1
        sides = int(kh_match.group(2))
        keep = int(kh_match.group(3))
        rolls = [random.randint(1, sides) for _ in range(max(n, 1))]
        kept = sorted(rolls, reverse=True)[:keep]
        total = sum(kept)
        return DiceResult(
            expression=expr,
            individual_rolls=rolls,
            modifier=0,
            total=total,
            advantage=False,
            disadvantage=False,
            kept_roll=None,
        )

    # Parse standard NdM±X
    std_match = re.fullmatch(r"(\d*)d(\d+)\s*([+-]\s*\d+)?", expr)
    if not std_match:
        raise ValueError(f"Invalid dice expression: {expr!r}")

    n_str = std_match.group(1)
    n = int(n_str) if n_str else 1
    sides = int(std_match.group(2))
    mod_str = std_match.group(3)
    modifier = int(mod_str.replace(" ", "")) if mod_str else 0

    if n == 0:
        return DiceResult(
            expression=expr,
            individual_rolls=[],
            modifier=modifier,
            total=modifier,
        )

    # Handle advantage/disadvantage on d20 checks
    kept_roll: int | None = None
    if sides == 20 and n == 1 and (advantage or disadvantage):
        r1 = random.randint(1, 20)
        r2 = random.randint(1, 20)
        if advantage:
            kept_roll = max(r1, r2)
        else:
            kept_roll = min(r1, r2)
        rolls = [r1, r2]
        total = kept_roll + modifier
        return DiceResult(
            expression=expr,
            individual_rolls=rolls,
            modifier=modifier,
            total=total,
            advantage=advantage,
            disadvantage=disadvantage,
            kept_roll=kept_roll,
        )

    rolls = [random.randint(1, sides) for _ in range(n)]
    total = sum(rolls) + modifier
    return DiceResult(
        expression=expr,
        individual_rolls=rolls,
        modifier=modifier,
        total=total,
        advantage=advantage,
        disadvantage=disadvantage,
        kept_roll=None,
    )
