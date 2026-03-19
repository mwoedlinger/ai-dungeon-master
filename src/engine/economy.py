"""Economy engine — buying, selling, crafting, and downtime activities."""
from __future__ import annotations

from src.engine.dice import roll_dice
from src.engine.rules import ability_check
from src.models.character import Character, Item


# ---------------------------------------------------------------------------
# SRD Equipment Prices (gp) — representative subset
# ---------------------------------------------------------------------------

EQUIPMENT_PRICES: dict[str, int] = {
    # Simple melee weapons
    "club": 0, "dagger": 2, "greatclub": 0, "handaxe": 5, "javelin": 1,
    "light hammer": 2, "mace": 5, "quarterstaff": 0, "sickle": 1, "spear": 1,
    # Martial melee weapons
    "battleaxe": 10, "flail": 10, "glaive": 20, "greataxe": 30, "greatsword": 50,
    "halberd": 20, "lance": 10, "longsword": 15, "maul": 10, "morningstar": 15,
    "pike": 5, "rapier": 25, "scimitar": 25, "shortsword": 10, "trident": 5,
    "war pick": 5, "warhammer": 15, "whip": 2,
    # Simple ranged weapons
    "crossbow, light": 25, "dart": 0, "shortbow": 25, "sling": 0,
    # Martial ranged weapons
    "blowgun": 10, "crossbow, hand": 75, "crossbow, heavy": 50, "longbow": 50,
    # Armor
    "padded armor": 5, "leather armor": 10, "studded leather": 45,
    "hide armor": 10, "chain shirt": 50, "scale mail": 50, "breastplate": 400,
    "half plate": 750, "ring mail": 30, "chain mail": 75, "splint armor": 200,
    "plate armor": 1500, "shield": 10,
    # Adventuring gear
    "backpack": 2, "bedroll": 1, "tinderbox": 1, "torch": 0, "rations": 1,
    "waterskin": 0, "rope, hempen": 1, "rope, silk": 10, "grappling hook": 2,
    "lantern, hooded": 5, "oil": 0, "piton": 0, "tent": 2, "crowbar": 2,
    "hammer": 1, "holy symbol": 5, "component pouch": 25, "arcane focus": 10,
    "healer's kit": 5, "caltrops": 1, "ball bearings": 1, "chain": 5,
    "lock": 10, "manacles": 2, "mirror": 5, "pole": 0, "spyglass": 1000,
    # Potions (common ones, priced by rarity)
    "potion of healing": 50, "potion of greater healing": 150,
    "potion of superior healing": 450, "potion of supreme healing": 1350,
    "antitoxin": 50,
    # Ammunition
    "arrows (20)": 1, "bolts (20)": 1, "sling bullets (20)": 0,
}

# Magic item price ranges by rarity
MAGIC_ITEM_PRICE_RANGES: dict[str, tuple[int, int]] = {
    "common": (50, 100),
    "uncommon": (100, 500),
    "rare": (500, 5000),
    "very_rare": (5000, 50000),
    "legendary": (50000, 500000),
}


def get_item_price(item_name: str, rarity: str = "common") -> int | None:
    """Look up an item's price. Returns None if unknown."""
    key = item_name.lower().strip()
    if key in EQUIPMENT_PRICES:
        return EQUIPMENT_PRICES[key]
    # Check magic item rarity pricing
    if rarity in MAGIC_ITEM_PRICE_RANGES:
        low, high = MAGIC_ITEM_PRICE_RANGES[rarity]
        return (low + high) // 2  # midpoint as default
    return None


def buy_item(
    character: Character,
    item_name: str,
    price: int,
    quantity: int = 1,
    weight: float = 0.0,
    description: str = "",
) -> dict:
    """Buy an item from a merchant. Deducts gold, adds to inventory."""
    total_cost = price * quantity
    if character.gold < total_cost:
        return {
            "success": False,
            "error": f"{character.name} has {character.gold}gp but needs {total_cost}gp.",
        }

    character.gold -= total_cost

    # Add to inventory (stack if existing)
    for item in character.inventory:
        if item.name.lower() == item_name.lower():
            item.quantity += quantity
            return {
                "success": True,
                "item": item_name,
                "quantity": item.quantity,
                "gold_spent": total_cost,
                "gold_remaining": character.gold,
            }

    character.inventory.append(
        Item(name=item_name, quantity=quantity, weight=weight, description=description)
    )
    return {
        "success": True,
        "item": item_name,
        "quantity": quantity,
        "gold_spent": total_cost,
        "gold_remaining": character.gold,
    }


def sell_item(
    character: Character,
    item_name: str,
    price: int,
    quantity: int = 1,
) -> dict:
    """Sell an item to a merchant. Adds gold, removes from inventory."""
    for i, item in enumerate(character.inventory):
        if item.name.lower() == item_name.lower():
            if item.quantity < quantity:
                return {
                    "success": False,
                    "error": f"{character.name} only has {item.quantity} {item_name}.",
                }
            item.quantity -= quantity
            if item.quantity == 0:
                character.inventory.pop(i)
            total_gold = price * quantity
            character.gold += total_gold
            return {
                "success": True,
                "item": item_name,
                "sold": quantity,
                "gold_earned": total_gold,
                "gold_remaining": character.gold,
            }

    return {"success": False, "error": f"{character.name} does not have {item_name!r}."}


# ---------------------------------------------------------------------------
# Crafting
# ---------------------------------------------------------------------------

# Crafting DC by item rarity
CRAFTING_DC: dict[str, int] = {
    "common": 10,
    "uncommon": 15,
    "rare": 20,
    "very_rare": 25,
    "legendary": 30,
}

# Crafting time in days by rarity
CRAFTING_DAYS: dict[str, int] = {
    "common": 1,
    "uncommon": 5,
    "rare": 20,
    "very_rare": 50,
    "legendary": 100,
}


def craft_item(
    character: Character,
    item_name: str,
    rarity: str = "common",
    tool_proficiency: str | None = None,
    material_cost: int | None = None,
) -> dict:
    """Attempt to craft an item. Requires tool proficiency and materials.

    Returns the check result and whether crafting succeeds.
    Material cost defaults to half the item's value.
    """
    dc = CRAFTING_DC.get(rarity, 15)
    days_required = CRAFTING_DAYS.get(rarity, 5)

    if material_cost is None:
        price_range = MAGIC_ITEM_PRICE_RANGES.get(rarity, (0, 100))
        material_cost = price_range[0] // 2  # half of low-end value

    if character.gold < material_cost:
        return {
            "success": False,
            "error": f"{character.name} needs {material_cost}gp for materials but has {character.gold}gp.",
        }

    # Check tool proficiency
    has_proficiency = (
        tool_proficiency is not None
        and tool_proficiency.lower() in [p.lower() for p in character.skill_proficiencies]
    )

    # Make the crafting check (INT-based)
    check = ability_check(
        character, "INT", dc,
        skill=tool_proficiency if has_proficiency else None,
    )

    if check.success:
        character.gold -= material_cost
        character.inventory.append(Item(name=item_name, description=f"Crafted ({rarity})"))
        return {
            "success": True,
            "crafted": item_name,
            "rarity": rarity,
            "check_roll": check.total,
            "dc": dc,
            "days_required": days_required,
            "material_cost": material_cost,
            "gold_remaining": character.gold,
        }
    else:
        # Failed — lose half the materials
        lost = material_cost // 2
        character.gold -= lost
        return {
            "success": False,
            "error": "Crafting failed.",
            "check_roll": check.total,
            "dc": dc,
            "materials_lost": lost,
            "gold_remaining": character.gold,
            "note": "Half the material cost is lost on failure.",
        }


# ---------------------------------------------------------------------------
# Downtime Activities
# ---------------------------------------------------------------------------

def downtime_training(
    character: Character,
    skill: str,
    days_spent: int,
    gold_per_day: int = 1,
) -> dict:
    """Train a new skill proficiency. Requires 250 days and gold (simplified).

    Each call represents a chunk of training days. When cumulative days
    reach 250, the proficiency is gained.
    """
    total_cost = gold_per_day * days_spent
    if character.gold < total_cost:
        return {
            "success": False,
            "error": f"Training costs {total_cost}gp ({days_spent} days × {gold_per_day}gp/day) but {character.name} has {character.gold}gp.",
        }

    if skill in character.skill_proficiencies:
        return {"success": False, "error": f"{character.name} is already proficient in {skill}."}

    character.gold -= total_cost

    # Track cumulative training days in class_resources
    key = f"training_{skill.lower()}"
    current = character.class_resources.get(key, 0)
    current += days_spent
    character.class_resources[key] = current

    if current >= 250:
        character.skill_proficiencies.append(skill)
        del character.class_resources[key]
        return {
            "success": True,
            "completed": True,
            "skill": skill,
            "gold_spent": total_cost,
            "gold_remaining": character.gold,
            "note": f"{character.name} is now proficient in {skill}!",
        }

    return {
        "success": True,
        "completed": False,
        "skill": skill,
        "days_trained": current,
        "days_remaining": 250 - current,
        "gold_spent": total_cost,
        "gold_remaining": character.gold,
    }


def downtime_carousing(character: Character) -> dict:
    """Carousing downtime activity. Roll on a random event table.

    Costs 10gp (modest) or 50gp (wealthy). Returns a random outcome.
    """
    cost = 10
    if character.gold < cost:
        return {"success": False, "error": f"{character.name} needs {cost}gp for carousing."}

    character.gold -= cost
    roll = roll_dice("1d20")
    value = roll.individual_rolls[0]

    if value <= 5:
        outcome = "trouble"
        description = "You wake up in an alley with a black eye and no memory of last night. You made an enemy."
    elif value <= 10:
        outcome = "neutral"
        description = "A quiet night of drinking and storytelling. Nothing notable happened."
    elif value <= 15:
        outcome = "contact"
        description = "You made a useful contact — someone who might have information or connections."
    elif value <= 18:
        outcome = "rumor"
        description = "You heard an interesting rumor about a nearby location or person of interest."
    else:
        outcome = "windfall"
        description = "Lady Luck smiled on you! A generous stranger bought drinks all night and left you a small gift."
        character.gold += 25

    return {
        "success": True,
        "roll": value,
        "outcome": outcome,
        "description": description,
        "gold_spent": cost,
        "gold_remaining": character.gold,
    }


def downtime_recuperate(character: Character) -> dict:
    """Recuperate downtime activity. Recover from lingering conditions.

    Spends 3 days recuperating: removes one non-permanent condition,
    grants advantage on saves vs disease/poison for 1 day.
    """
    removable = [c for c in character.conditions if c not in ("dead", "cursed")]
    removed = None
    if removable:
        removed = removable[0]
        character.conditions.remove(removed)

    # Full HP restore as part of recuperation
    character.hp = character.max_hp

    return {
        "success": True,
        "hp_restored": character.max_hp,
        "condition_removed": removed,
        "days_spent": 3,
        "note": "Recuperation complete. Full HP restored." + (
            f" {removed} condition removed." if removed else ""
        ),
    }
