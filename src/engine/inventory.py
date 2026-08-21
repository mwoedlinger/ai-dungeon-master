"""Inventory & equipment controller — the single high-level item API.

A transport-agnostic façade over the authoritative ``Character`` storage,
shared by the LLM tool layer and (next) the CLI interactive screens and the web
UI. It owns the *intuitive* rules — which actions are valid for an item right
now, attunement limits, using consumables, giving between party members — and
returns structured results the views render. Storage stays the legacy
``Character`` containers; this class is the seam that lets the UI treat them as
one unified, contextual inventory. See ``docs/DESIGN_INVENTORY_UI.md``.

No rendering, no I/O.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from src.models.items import (
    MAX_ATTUNEMENT,
    ItemCategory,
    Slot,
    consumable_from_properties,
)

if TYPE_CHECKING:
    from src.models.character import Character


class ItemAction(str, Enum):
    UNEQUIP = "unequip"
    USE = "use"
    DROP = "drop"
    GIVE = "give"
    SPLIT = "split"
    EXAMINE = "examine"


class ActionResult(BaseModel):
    success: bool
    message: str = ""
    error: str | None = None
    data: dict[str, Any] = {}


class SlotView(BaseModel):
    slot: Slot
    item_id: str | None = None
    item_name: str | None = None


class ItemView(BaseModel):
    id: str
    name: str
    category: ItemCategory
    quantity: int
    weight: float
    equipped: bool
    description: str = ""
    actions: list[ItemAction] = []


class InventoryView(BaseModel):
    """Everything a screen needs to render one character's inventory."""

    character_id: str
    character_name: str
    gold: int
    carry_weight: float
    capacity: float
    encumbrance_tier: str
    attunement_used: int
    attunement_max: int = MAX_ATTUNEMENT
    slots: list[SlotView]
    items: list[ItemView]


# Item-id prefixes map a view id back to its legacy container.
_W, _A, _S, _M, _I = "w", "a", "s", "m", "i"


def _slug(name: str) -> str:
    return name.strip().lower()


class InventoryController:
    """High-level item management over a single game's authoritative state."""

    def __init__(self, game_state) -> None:
        self.gs = game_state

    # -- read ------------------------------------------------------------

    def view(self, char_id: str) -> InventoryView:
        from src.engine.rules import encumbrance_status

        char = self.gs.get_character(char_id)
        enc = encumbrance_status(char)

        slots = [
            SlotView(slot=Slot.MAIN_HAND,
                     item_id=(f"{_W}:{_slug(char.weapons[0].name)}" if char.weapons else None),
                     item_name=(char.weapons[0].name if char.weapons else None)),
            SlotView(slot=Slot.OFF_HAND,
                     item_id=(f"{_S}:shield" if char.shield else None),
                     item_name=("Shield" if char.shield else None)),
            SlotView(slot=Slot.ARMOR,
                     item_id=(f"{_A}:{_slug(char.armor.name)}" if char.armor else None),
                     item_name=(char.armor.name if char.armor else None)),
        ]

        items = [self._item_view(char_id, iv) for iv in self._iter_items(char)]
        return InventoryView(
            character_id=char_id,
            character_name=char.name,
            gold=char.gold,
            carry_weight=round(enc["current_weight"], 1),
            capacity=enc["capacity"],
            encumbrance_tier=enc["tier"],
            attunement_used=len(char.attuned_items),
            slots=slots,
            items=items,
        )

    def _iter_items(self, char) -> list[tuple[str, str, ItemCategory, int, float, bool, str]]:
        """Flatten the legacy containers into (id, name, category, qty, weight, equipped, desc)."""
        rows: list[tuple] = []
        for w in char.weapons:
            rows.append((f"{_W}:{_slug(w.name)}", w.name, ItemCategory.WEAPON, 1, 0.0, True,
                         f"{w.damage_dice} {w.damage_type}"))
        if char.armor:
            rows.append((f"{_A}:{_slug(char.armor.name)}", char.armor.name, ItemCategory.ARMOR, 1, 0.0,
                         True, f"AC {char.armor.base_ac} ({char.armor.armor_type})"))
        if char.shield:
            rows.append((f"{_S}:shield", "Shield", ItemCategory.SHIELD, 1, 0.0, True, "+2 AC"))
        for mi in char.attuned_items:
            rows.append((f"{_M}:{_slug(mi.name)}", mi.name, ItemCategory.MAGIC, 1, 0.0, True, mi.description))
        for it in char.inventory:
            cat = ItemCategory.CONSUMABLE if consumable_from_properties(it.properties) else ItemCategory.GEAR
            rows.append((f"{_I}:{_slug(it.name)}", it.name, cat, it.quantity, it.weight, False, it.description))
        return rows

    def _item_view(self, char_id: str, row: tuple) -> ItemView:
        iid, name, cat, qty, weight, equipped, desc = row
        return ItemView(
            id=iid, name=name, category=cat, quantity=qty, weight=weight,
            equipped=equipped, description=desc, actions=self.actions_for(char_id, iid),
        )

    # -- contextual actions ----------------------------------------------

    def actions_for(self, char_id: str, item_id: str) -> list[ItemAction]:
        """Only the actions legal for this item right now — the source of the
        screens' intuitiveness (a sword never offers Use; Give only appears when
        there is another party member)."""
        char = self.gs.get_character(char_id)
        resolved = self._resolve(char, item_id)
        if resolved is None:
            return []
        kind, obj = resolved

        actions: list[ItemAction] = [ItemAction.EXAMINE]
        has_ally = self._other_player_id(char_id) is not None

        if kind in ("weapon", "armor", "shield", "magic"):
            actions.append(ItemAction.UNEQUIP)
            if kind == "weapon" and has_ally:
                actions.append(ItemAction.GIVE)
        else:  # inventory item
            if consumable_from_properties(obj.properties):
                actions.append(ItemAction.USE)
            actions.append(ItemAction.DROP)
            if has_ally:
                actions.append(ItemAction.GIVE)
            if obj.quantity > 1:
                actions.append(ItemAction.SPLIT)
        return actions

    # -- apply -----------------------------------------------------------

    def apply(self, char_id: str, action: ItemAction | str, item_id: str, **kwargs) -> ActionResult:
        action = ItemAction(action)
        char = self.gs.get_character(char_id)
        resolved = self._resolve(char, item_id)
        if resolved is None:
            return ActionResult(success=False, error=f"Item {item_id!r} not found on {char.name}.")

        if action not in self.actions_for(char_id, item_id):
            kind, obj = resolved
            name = obj.name if kind != "shield" else "Shield"
            return ActionResult(success=False, error=f"Cannot {action.value} {name} right now.")

        kind, obj = resolved
        if action == ItemAction.EXAMINE:
            return self._examine(kind, obj)
        if action == ItemAction.UNEQUIP:
            return self._unequip(char, kind, obj)
        if action == ItemAction.USE:
            return self._use(char, obj)
        if action == ItemAction.DROP:
            return self._drop(char_id, char, obj, kwargs.get("quantity"))
        if action == ItemAction.GIVE:
            return self._give(char_id, char, kind, obj, kwargs.get("to_id"), kwargs.get("quantity", 1))
        if action == ItemAction.SPLIT:
            return self._split(char, obj, kwargs.get("quantity", 1))
        return ActionResult(success=False, error="Unsupported action.")

    # -- resolution ------------------------------------------------------

    def _resolve(self, char, item_id: str) -> tuple[str, Any] | None:
        """Map a view id back to its legacy object: (kind, obj)."""
        try:
            prefix, slug = item_id.split(":", 1)
        except ValueError:
            return None
        if prefix == _W:
            obj = next((w for w in char.weapons if _slug(w.name) == slug), None)
            return ("weapon", obj) if obj else None
        if prefix == _A:
            return ("armor", char.armor) if char.armor and _slug(char.armor.name) == slug else None
        if prefix == _S:
            return ("shield", None) if char.shield else None
        if prefix == _M:
            obj = next((m for m in char.attuned_items if _slug(m.name) == slug), None)
            return ("magic", obj) if obj else None
        if prefix == _I:
            obj = next((it for it in char.inventory if _slug(it.name) == slug), None)
            return ("inventory", obj) if obj else None
        return None

    def _other_player_id(self, char_id: str) -> str | None:
        others = [pid for pid in self.gs.player_character_ids if pid != char_id]
        return others[0] if others else None

    # -- handlers --------------------------------------------------------

    def _examine(self, kind: str, obj) -> ActionResult:
        if kind == "shield":
            return ActionResult(success=True, message="A sturdy shield. +2 AC while equipped.")
        desc = getattr(obj, "description", "") or f"{obj.name} — nothing remarkable."
        return ActionResult(success=True, message=desc)

    def _unequip(self, char, kind: str, obj) -> ActionResult:
        from src.engine.rules import recalculate_ac

        if kind == "weapon":
            char.weapons.remove(obj)
            self.gs.add_item(char.id, obj.name)
            return ActionResult(success=True, message=f"{char.name} unequips {obj.name}.")
        if kind == "armor":
            name = obj.name
            char.armor = None
            char.ac = recalculate_ac(char)
            self.gs.add_item(char.id, name)
            return ActionResult(success=True, message=f"{char.name} removes {name}.",
                                data={"new_ac": char.ac})
        if kind == "shield":
            char.shield = False
            char.ac = recalculate_ac(char)
            return ActionResult(success=True, message=f"{char.name} stows their shield.",
                                data={"new_ac": char.ac})
        if kind == "magic":
            char.attuned_items.remove(obj)
            return ActionResult(success=True, message=f"{char.name} ends attunement to {obj.name}.")
        return ActionResult(success=False, error="Nothing to unequip.")

    def _use(self, char, item) -> ActionResult:
        effect = consumable_from_properties(item.properties)
        if effect is None:
            return ActionResult(success=False, error=f"{item.name} cannot be used.")

        outcome: dict[str, Any] = {}
        message = f"{char.name} uses {item.name}."
        if effect.heal:
            from src.engine.dice import roll_dice
            from src.engine.rules import apply_healing
            rolled = roll_dice(effect.heal).total
            res = apply_healing(char, rolled)
            if not res.get("success", True):
                return ActionResult(success=False, error=res.get("error", "Healing failed."))
            outcome = res
            message = f"{char.name} uses {item.name} — heals {rolled} HP ({char.hp}/{char.max_hp})."
        elif effect.condition:
            from src.engine.rules import apply_condition
            apply_condition(char, effect.condition, combat_state=self.gs.combat if self.gs.combat.active else None)
            message = f"{char.name} uses {item.name} — gains {effect.condition}."

        self.gs.remove_item(char.id, item.name, 1)
        remaining = next((it.quantity for it in char.inventory if it.name == item.name), 0)
        outcome["remaining"] = remaining
        return ActionResult(success=True, message=message, data=outcome)

    def _drop(self, char_id: str, char, item, quantity: int | None) -> ActionResult:
        qty = item.quantity if quantity is None else min(quantity, item.quantity)
        self.gs.remove_item(char_id, item.name, qty)
        return ActionResult(success=True, message=f"{char.name} drops {qty}× {item.name}.",
                            data={"dropped": qty})

    def _give(self, char_id: str, char, kind: str, obj, to_id: str | None, quantity: int) -> ActionResult:
        to_id = to_id or self._other_player_id(char_id)
        if to_id is None:
            return ActionResult(success=False, error="No one to give it to.")
        recipient = self.gs.get_character(to_id)

        if kind == "weapon":
            char.weapons.remove(obj)
            recipient.weapons.append(obj)
            return ActionResult(success=True, message=f"{char.name} gives {obj.name} to {recipient.name}.",
                                data={"to": to_id, "quantity": 1})

        # inventory item: move, preserving weight/description/effect properties
        give_qty = min(quantity, obj.quantity)
        existing = next((it for it in recipient.inventory if _slug(it.name) == _slug(obj.name)), None)
        if existing is not None:
            existing.quantity += give_qty
        else:
            moved = obj.model_copy(deep=True)
            moved.quantity = give_qty
            recipient.inventory.append(moved)
        self.gs.remove_item(char_id, obj.name, give_qty)
        return ActionResult(success=True,
                            message=f"{char.name} gives {give_qty}× {obj.name} to {recipient.name}.",
                            data={"to": to_id, "quantity": give_qty})

    def _split(self, char, item, quantity: int) -> ActionResult:
        if quantity < 1 or quantity >= item.quantity:
            return ActionResult(success=False, error="Cannot split that stack.")
        # Splitting an in-place stack is a no-op on legacy storage (a single
        # named stack), but we expose it so the UI can stage a give of part of
        # a stack. Here it simply confirms the addressable sub-quantity.
        return ActionResult(success=True, message=f"{quantity}× {item.name} ready to move.",
                            data={"quantity": quantity, "remaining": item.quantity - quantity})
