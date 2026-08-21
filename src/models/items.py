"""Item view/DTO layer for inventory & character management.

The game's authoritative storage remains the legacy ``Character`` containers
(``weapons``/``armor``/``shield``/``inventory``/``attuned_items``). This module
provides the *presentation* vocabulary the inventory screens and the
:class:`~src.engine.inventory.InventoryController` speak — categories, equipment
slots, and the parsed effect of a consumable — without introducing a second
source of truth. See ``docs/DESIGN_INVENTORY_UI.md``.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

MAX_ATTUNEMENT = 3


class ItemCategory(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    SHIELD = "shield"
    CONSUMABLE = "consumable"
    MAGIC = "magic"
    GEAR = "gear"


class Slot(str, Enum):
    MAIN_HAND = "main_hand"
    OFF_HAND = "off_hand"
    ARMOR = "armor"
    ATTUNEMENT = "attunement"


class ConsumableEffect(BaseModel):
    """What using a consumable does. At most one mechanical effect fires."""

    heal: str | None = None        # dice expression, e.g. "2d4+2"
    cast_spell: str | None = None  # spell name resolved through the engine
    condition: str | None = None   # condition applied to the user (e.g. "blessed")
    note: str = ""                 # free-text for purely narrative effects

    @property
    def is_mechanical(self) -> bool:
        return bool(self.heal or self.cast_spell or self.condition)


# Keys recognised inside a legacy ``Item.properties`` dict that mark it usable.
_EFFECT_KEYS = ("heal", "cast_spell", "condition")


def consumable_from_properties(properties: dict) -> ConsumableEffect | None:
    """Parse a legacy ``Item.properties`` dict into a :class:`ConsumableEffect`.

    Returns ``None`` when the item carries no recognised use-effect, so callers
    can treat it as ordinary gear. This is how consumables are modelled without
    a dedicated storage type: a potion is an ``Item`` whose ``properties`` hold
    ``{"heal": "2d4+2"}``.
    """
    if not properties:
        return None
    if not any(k in properties for k in _EFFECT_KEYS):
        return None
    return ConsumableEffect(
        heal=properties.get("heal"),
        cast_spell=properties.get("cast_spell"),
        condition=properties.get("condition"),
        note=properties.get("note", ""),
    )
