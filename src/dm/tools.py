"""Tool schemas, action costs, and ToolDispatcher."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from src.data.srd_client import get_monster_template, get_spell, lookup_srd as _lookup_srd
from src.engine import combat as combat_engine
from src.engine import rest as rest_engine
from src.engine.rules import (
    ability_check,
    apply_condition,
    apply_damage,
    apply_healing,
    remove_condition,
    saving_throw,
    use_lay_on_hands,
    use_second_wind,
)
from src.engine.spells import resolve_spell
from src.log.event_log import EventLog

if TYPE_CHECKING:
    from src.engine.game_state import GameState


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_DICE_AND_CHECK_TOOLS = [
    {
        "name": "roll_dice",
        "description": "Roll dice using standard notation. Use for any random outcome not covered by other tools.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dice_expr": {"type": "string", "description": "e.g. '2d6+3', '1d20', '4d6kh3' (keep highest 3)"},
                "reason": {"type": "string", "description": "Why this roll is being made (displayed to players)"},
            },
            "required": ["dice_expr", "reason"],
        },
    },
    {
        "name": "ability_check",
        "description": "Make an ability check for a character against a DC. Use for any uncertain action: climbing, persuading, picking locks, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "ability": {"type": "string", "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"]},
                "skill": {"type": "string", "description": "Skill name if applicable: Perception, Athletics, Stealth, etc."},
                "dc": {"type": "integer", "description": "Difficulty Class. Easy=10, Medium=15, Hard=20, Very Hard=25"},
                "advantage": {"type": "boolean", "default": False},
                "disadvantage": {"type": "boolean", "default": False},
            },
            "required": ["character_id", "ability", "dc"],
        },
    },
    {
        "name": "saving_throw",
        "description": "Make a saving throw for a character against a DC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "ability": {"type": "string", "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"]},
                "dc": {"type": "integer"},
                "advantage": {"type": "boolean", "default": False},
                "disadvantage": {"type": "boolean", "default": False},
            },
            "required": ["character_id", "ability", "dc"],
        },
    },
]

_COMBAT_TOOLS = [
    {
        "name": "start_combat",
        "description": "Begin combat encounter. Rolls initiative for all participants and sets turn order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "participant_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "All character/monster IDs entering combat",
                },
                "monster_templates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Monster template IDs to spawn (e.g. ['goblin', 'goblin']). Will be assigned IDs automatically.",
                },
            },
            "required": ["participant_ids"],
        },
    },
    {
        "name": "attack",
        "description": "Make a weapon attack. Costs an action. Handles hit/miss and damage automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "attacker_id": {"type": "string"},
                "target_id": {"type": "string"},
                "weapon_name": {"type": "string"},
                "advantage": {"type": "boolean", "default": False},
                "disadvantage": {"type": "boolean", "default": False},
            },
            "required": ["attacker_id", "target_id", "weapon_name"],
        },
    },
    {
        "name": "cast_spell",
        "description": "Cast a spell. Validates spell slots, applies effects. For NARRATIVE spells, deducts the slot and returns description for narration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caster_id": {"type": "string"},
                "spell_name": {"type": "string"},
                "spell_level": {"type": "integer", "description": "Level to cast at (for upcasting). Use 0 for cantrips."},
                "target_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["caster_id", "spell_name", "spell_level", "target_ids"],
        },
    },
    {
        "name": "apply_damage",
        "description": "Apply damage directly (environmental hazards, traps, fall damage). For weapon/spell damage, use attack or cast_spell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "amount": {"type": "integer"},
                "damage_type": {"type": "string", "description": "fire, piercing, bludgeoning, etc."},
            },
            "required": ["target_id", "amount", "damage_type"],
        },
    },
    {
        "name": "apply_healing",
        "description": "Heal a character directly (potions, resting effects). For spell healing, use cast_spell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "amount": {"type": "integer"},
            },
            "required": ["target_id", "amount"],
        },
    },
    {
        "name": "apply_condition",
        "description": "Apply a condition (blinded, charmed, frightened, prone, etc.) to a character.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "condition": {"type": "string"},
                "duration_rounds": {"type": "integer", "description": "Omit for indefinite duration"},
            },
            "required": ["target_id", "condition"],
        },
    },
    {
        "name": "remove_condition",
        "description": "Remove a condition from a character.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
                "condition": {"type": "string"},
            },
            "required": ["target_id", "condition"],
        },
    },
    {
        "name": "get_monster_actions",
        "description": "Get the list of actions a monster can take. Call this before acting as a monster to ensure you only use real abilities.",
        "input_schema": {
            "type": "object",
            "properties": {"monster_id": {"type": "string"}},
            "required": ["monster_id"],
        },
    },
    {
        "name": "death_save",
        "description": "Roll a death saving throw for an unconscious player character.",
        "input_schema": {
            "type": "object",
            "properties": {"character_id": {"type": "string"}},
            "required": ["character_id"],
        },
    },
    {
        "name": "end_turn",
        "description": "End the current combatant's turn. Advances to next in initiative order.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "end_combat",
        "description": "End the combat encounter. Call when all enemies are defeated or combat ends narratively.",
        "input_schema": {
            "type": "object",
            "properties": {
                "xp_awarded": {"type": "integer", "description": "Total XP to split among player characters"},
            },
            "required": ["xp_awarded"],
        },
    },
    {
        "name": "use_legendary_action",
        "description": "Use a boss monster's legendary action between other combatants' turns. Legendary actions refresh at the start of the monster's turn.",
        "input_schema": {
            "type": "object",
            "properties": {
                "monster_id": {"type": "string"},
                "action_name": {"type": "string", "description": "Name of the legendary action to use"},
                "target_id": {"type": "string", "description": "Target of the action, if applicable"},
            },
            "required": ["monster_id", "action_name"],
        },
    },
    {
        "name": "use_legendary_resistance",
        "description": "Use a boss monster's legendary resistance to automatically succeed on a saving throw. Limited uses per day.",
        "input_schema": {
            "type": "object",
            "properties": {
                "monster_id": {"type": "string"},
            },
            "required": ["monster_id"],
        },
    },
]

_STATE_TOOLS = [
    {
        "name": "get_character_sheet",
        "description": "Retrieve full character stats. Use when you need exact numbers (HP, AC, spell slots, inventory).",
        "input_schema": {
            "type": "object",
            "properties": {"character_id": {"type": "string"}},
            "required": ["character_id"],
        },
    },
    {
        "name": "take_short_rest",
        "description": "Character takes a short rest. Spends hit dice to recover HP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "hit_dice_to_spend": {"type": "integer"},
            },
            "required": ["character_id", "hit_dice_to_spend"],
        },
    },
    {
        "name": "take_long_rest",
        "description": "Character takes a long rest. Full HP, spell slot reset, partial hit dice recovery.",
        "input_schema": {
            "type": "object",
            "properties": {"character_id": {"type": "string"}},
            "required": ["character_id"],
        },
    },
    {
        "name": "add_item",
        "description": "Add an item to a character's inventory. Returns carry weight and warns if encumbered or over capacity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "item_name": {"type": "string"},
                "quantity": {"type": "integer", "default": 1},
                "weight": {"type": "number", "default": 0, "description": "Weight per item in lbs"},
                "description": {"type": "string", "default": ""},
            },
            "required": ["character_id", "item_name"],
        },
    },
    {
        "name": "remove_item",
        "description": "Remove an item from a character's inventory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "item_name": {"type": "string"},
                "quantity": {"type": "integer", "default": 1},
            },
            "required": ["character_id", "item_name"],
        },
    },
    {
        "name": "award_xp",
        "description": "Award XP to player characters. Returns level-up info if applicable.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_ids": {"type": "array", "items": {"type": "string"}},
                "xp": {"type": "integer"},
            },
            "required": ["character_ids", "xp"],
        },
    },
    {
        "name": "update_quest",
        "description": "Update quest status or mark an objective complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quest_id": {"type": "string"},
                "completed_objective": {"type": "string"},
                "new_status": {"type": "string", "enum": ["active", "completed", "failed"]},
            },
            "required": ["quest_id"],
        },
    },
    {
        "name": "set_location",
        "description": "Instantly move the party to a new location (no travel time). Use travel_to_location instead for overland travel between distant locations. Use set_location only for entering sub-locations (tavern inside a village) or teleportation.",
        "input_schema": {
            "type": "object",
            "properties": {"location_id": {"type": "string"}},
            "required": ["location_id"],
        },
    },
    {
        "name": "query_world_lore",
        "description": "Look up campaign-specific information: location details, NPC profiles, faction info, plot hooks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {"type": "string", "enum": ["location", "npc", "faction", "plot_hook"]},
                "id": {"type": "string"},
            },
            "required": ["query_type", "id"],
        },
    },
    {
        "name": "save_game",
        "description": "Persist current game state to disk. Call at natural stopping points.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "improve_ability_score",
        "description": "Apply an Ability Score Improvement from leveling up. Call when a character gains an ASI (levels 4, 8, 12, 16, 19, and Fighter 6/14). Ask the player which ability to improve before calling.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "ability": {"type": "string", "enum": ["STR", "DEX", "CON", "INT", "WIS", "CHA"]},
                "increase_by": {
                    "type": "integer",
                    "enum": [1, 2],
                    "description": "Two +1s spread across two calls, or one +2 in a single call",
                },
            },
            "required": ["character_id", "ability", "increase_by"],
        },
    },
    {
        "name": "use_action_surge",
        "description": "Use Action Surge (Fighter). Grants an additional action this turn. Consumes one charge. ONLY call when the player explicitly requests it.",
        "input_schema": {
            "type": "object",
            "properties": {"character_id": {"type": "string"}},
            "required": ["character_id"],
        },
    },
    {
        "name": "use_second_wind",
        "description": "Use Second Wind (Fighter). Heal 1d10 + fighter level HP as a bonus action. One use per short rest.",
        "input_schema": {
            "type": "object",
            "properties": {"character_id": {"type": "string"}},
            "required": ["character_id"],
        },
    },
    {
        "name": "use_lay_on_hands",
        "description": "Use Lay on Hands (Paladin). Touch a creature and heal HP from your healing pool (level × 5 HP total, restored on long rest).",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string", "description": "The Paladin using Lay on Hands"},
                "target_id": {"type": "string", "description": "Character to heal"},
                "amount": {"type": "integer", "description": "HP to restore from pool"},
            },
            "required": ["character_id", "target_id", "amount"],
        },
    },
    {
        "name": "learn_spell",
        "description": "Add a spell to a character's known spells. Use after level-up when a character gains new spells.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "spell_name": {"type": "string"},
            },
            "required": ["character_id", "spell_name"],
        },
    },
    {
        "name": "get_random_encounter",
        "description": "Roll a random encounter for the current or specified location. Returns encounter details and monster IDs to use with start_combat().",
        "input_schema": {
            "type": "object",
            "properties": {
                "location_id": {"type": "string", "description": "Location to roll encounter for. Defaults to current location."},
            },
        },
    },
    {
        "name": "lookup_srd",
        "description": "Look up any D&D 5e SRD data: monsters, spells, equipment, magic-items, classes, races, conditions, skills. Use to get stats before spawning a monster, check spell details, look up equipment properties, or find magic item descriptions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["monsters", "spells", "equipment", "magic-items", "classes", "races", "conditions", "skills", "features"],
                    "description": "Type of SRD data to look up",
                },
                "query": {
                    "type": "string",
                    "description": "Name to look up (e.g. 'goblin', 'fireball', 'longsword'). Use standard SRD names.",
                },
            },
            "required": ["category", "query"],
        },
    },
    {
        "name": "search_srd",
        "description": "Search/list available SRD entities by category. Use when you need to find what's available (e.g. all CR 1 monsters, all level-2 spells).",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["monsters", "spells", "equipment", "magic-items", "classes", "races", "conditions", "skills", "features"],
                },
                "query": {
                    "type": "string",
                    "description": "Optional search filter. Empty string returns all entries.",
                    "default": "",
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "record_event",
        "description": "Record a significant event in the world journal. Call after: NPC conversations (summarize what was discussed/learned), combat outcomes, important discoveries, story decisions, faction changes. Write a concise one-line summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event": {"type": "string", "description": "Concise summary: 'Elder Mora revealed her son is cursed' or 'Party defeated 3 ghouls in the Bleakwood'"},
                "location_id": {"type": "string", "description": "Location where this happened (defaults to current)"},
                "involved_npcs": {"type": "array", "items": {"type": "string"}, "description": "NPC IDs involved"},
                "importance": {"type": "string", "enum": ["major", "minor"], "description": "major = story-changing event, minor = local detail"},
            },
            "required": ["event"],
        },
    },
    {
        "name": "update_npc_attitude",
        "description": "Update how an NPC feels about the party. Call when disposition shifts due to player actions (persuasion, intimidation, helping, betrayal).",
        "input_schema": {
            "type": "object",
            "properties": {
                "npc_id": {"type": "string", "description": "NPC identifier from campaign data"},
                "disposition": {"type": "string", "enum": ["friendly", "neutral", "hostile", "fearful"]},
                "notes": {"type": "string", "description": "Brief reason: 'Party rescued her cat' or 'Intimidated into silence'"},
            },
            "required": ["npc_id", "disposition"],
        },
    },
    {
        "name": "set_world_flag",
        "description": "Set a world state flag for tracking branching state. Supports binary flags ('bridge_destroyed': 'true'), numeric values ('orc_threat': '45'), and timestamped events ('bridge_collapsed_day': '7'). Use for any persistent world state that affects future events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "flag": {"type": "string", "description": "Snake_case flag name: 'bridge_destroyed', 'orc_threat', 'town_prosperity'"},
                "value": {"type": "string", "default": "true", "description": "Value to set. Use 'true'/'false' for binary, numeric strings for quantities, 'day_N' for timestamps."},
            },
            "required": ["flag"],
        },
    },
    {
        "name": "recall_events",
        "description": "Query the world journal for past events. Use to remember what happened at a location, with an NPC, or recently. Call this BEFORE NPC dialogue to recall prior interactions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {"type": "string", "enum": ["location", "npc", "recent"], "description": "What to look up"},
                "query_id": {"type": "string", "description": "Location ID or NPC ID (required for location/npc queries)"},
                "limit": {"type": "integer", "default": 10, "description": "Max entries to return"},
            },
            "required": ["query_type"],
        },
    },
    {
        "name": "start_npc_dialogue",
        "description": "Start an in-character dialogue with an NPC. Returns the NPC's response. Resolve skill checks (Persuasion, Insight) BEFORE calling this and pass results in context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "npc_id": {"type": "string", "description": "NPC identifier from campaign data"},
                "player_input": {"type": "string", "description": "What the player says or does"},
                "context": {"type": "string", "description": "DM context: check results, scene details, etc."},
            },
            "required": ["npc_id", "player_input"],
        },
    },
    {
        "name": "continue_npc_dialogue",
        "description": "Continue an existing dialogue with an NPC. Uses the same session from start_npc_dialogue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "npc_id": {"type": "string"},
                "player_input": {"type": "string"},
            },
            "required": ["npc_id", "player_input"],
        },
    },
    {
        "name": "get_location_treasure",
        "description": "Check what treasure is placed at a location (DM eyes only). Shows undiscovered items with their discovery conditions (DC checks, hidden locations). Use this when players search an area or investigate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location_id": {"type": "string", "description": "Location to check. Defaults to current location."},
                "include_found": {"type": "boolean", "default": False, "description": "Include already-found items"},
            },
        },
    },
    {
        "name": "claim_treasure",
        "description": "Mark a treasure item as found and add it to a character's inventory. Call after the player discovers and picks up a pre-placed item. For magic items requiring attunement, also call attune_item() during a short rest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location_id": {"type": "string", "description": "Location where the treasure is. Defaults to current."},
                "item_name": {"type": "string", "description": "Name of the treasure item"},
                "character_id": {"type": "string", "description": "Character who picks it up"},
            },
            "required": ["item_name", "character_id"],
        },
    },
    {
        "name": "advance_time",
        "description": "Advance the in-game clock. Call during travel, resting, or downtime. Returns current time, day/night status, and transition events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "default": 0, "description": "Hours to advance"},
                "minutes": {"type": "integer", "default": 0, "description": "Minutes to advance"},
            },
        },
    },
    {
        "name": "attune_item",
        "description": "Attune a magic item to a character. Max 3 attuned items per character (5e rules). Requires a short rest narratively.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "item_name": {"type": "string", "description": "Name of the magic item"},
                "item_type": {"type": "string", "enum": ["weapon", "armor", "shield", "wondrous", "ring", "staff", "rod", "wand"], "description": "Type of magic item"},
                "bonus": {"type": "integer", "default": 0, "description": "+1/+2/+3 bonus (weapons: attack+damage, armor: AC)"},
                "rarity": {"type": "string", "enum": ["common", "uncommon", "rare", "very_rare", "legendary"], "default": "uncommon"},
                "requires_attunement": {"type": "boolean", "default": True},
                "properties": {"type": "object", "default": {}, "description": "Special properties, e.g. {\"daily_spell\": \"fireball\", \"charges\": 3}"},
                "description": {"type": "string", "default": ""},
            },
            "required": ["character_id", "item_name", "item_type"],
        },
    },
    {
        "name": "unattune_item",
        "description": "Remove attunement from a magic item, freeing the attunement slot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "item_name": {"type": "string"},
            },
            "required": ["character_id", "item_name"],
        },
    },
    {
        "name": "equip_armor",
        "description": "Equip armor from inventory, replacing current armor (returned to inventory). Recalculates AC. Use 'unequip' to just remove current armor without replacing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "item_name": {"type": "string", "description": "Armor name from inventory, or 'unequip' to remove current armor"},
                "base_ac": {"type": "integer", "description": "Armor base AC (e.g. 11 for leather, 14 for chain shirt, 16 for chain mail, 18 for plate)"},
                "armor_type": {"type": "string", "enum": ["light", "medium", "heavy"], "description": "Armor category"},
                "stealth_disadvantage": {"type": "boolean", "default": False},
                "strength_requirement": {"type": "integer", "description": "Minimum STR to wear without speed penalty"},
            },
            "required": ["character_id", "item_name"],
        },
    },
    {
        "name": "equip_shield",
        "description": "Equip or unequip a shield (+2 AC). Recalculates AC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "equip": {"type": "boolean", "description": "True to equip, False to unequip"},
            },
            "required": ["character_id", "equip"],
        },
    },
    {
        "name": "equip_weapon",
        "description": "Add a weapon to a character's active weapon list (from inventory or loot). To remove, use unequip_weapon.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "weapon_name": {"type": "string"},
                "damage_dice": {"type": "string", "description": "e.g. '1d8', '2d6'"},
                "damage_type": {"type": "string", "description": "e.g. 'slashing', 'piercing', 'bludgeoning'"},
                "properties": {"type": "array", "items": {"type": "string"}, "default": [], "description": "e.g. ['finesse', 'light'] or ['ranged', 'heavy']"},
                "range_normal": {"type": "integer", "description": "Normal range in feet (ranged weapons)"},
                "range_long": {"type": "integer", "description": "Long range in feet (ranged weapons)"},
            },
            "required": ["character_id", "weapon_name", "damage_dice", "damage_type"],
        },
    },
    {
        "name": "unequip_weapon",
        "description": "Remove a weapon from a character's active weapon list (returns to inventory).",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "weapon_name": {"type": "string"},
            },
            "required": ["character_id", "weapon_name"],
        },
    },
]

_ECONOMY_TOOLS = [
    {
        "name": "buy_item",
        "description": "Buy an item from a merchant. Deducts gold, adds to inventory. Use get_item_price to check prices first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "item_name": {"type": "string"},
                "price": {"type": "integer", "description": "Price per item in gold pieces"},
                "quantity": {"type": "integer", "default": 1},
                "weight": {"type": "number", "default": 0, "description": "Weight per item in lbs"},
                "description": {"type": "string", "default": ""},
            },
            "required": ["character_id", "item_name", "price"],
        },
    },
    {
        "name": "sell_item",
        "description": "Sell an item to a merchant. Removes from inventory, adds gold. Typically items sell for half their purchase price.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "item_name": {"type": "string"},
                "price": {"type": "integer", "description": "Sale price per item in gold pieces"},
                "quantity": {"type": "integer", "default": 1},
            },
            "required": ["character_id", "item_name", "price"],
        },
    },
    {
        "name": "get_item_price",
        "description": "Look up an item's standard price from the SRD equipment list. Returns None if item is not in the database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_name": {"type": "string"},
                "rarity": {"type": "string", "default": "common", "description": "For magic items: common, uncommon, rare, very_rare, legendary"},
            },
            "required": ["item_name"],
        },
    },
    {
        "name": "craft_item",
        "description": "Attempt to craft an item. Requires tool proficiency, materials (gold), and time. Makes an INT check against a DC based on item rarity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "item_name": {"type": "string"},
                "rarity": {"type": "string", "enum": ["common", "uncommon", "rare", "very_rare", "legendary"], "default": "common"},
                "tool_proficiency": {"type": "string", "description": "Required tool proficiency (e.g. 'Smith\\'s Tools', 'Herbalism Kit')"},
                "material_cost": {"type": "integer", "description": "Gold cost for materials. Defaults to half the item value."},
            },
            "required": ["character_id", "item_name"],
        },
    },
    {
        "name": "downtime_training",
        "description": "Train a new skill proficiency during downtime. Requires 250 days total and gold. Each call represents one chunk of training. Track progress over multiple sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "skill": {"type": "string", "description": "Skill to train (e.g. 'Perception', 'Stealth')"},
                "days_spent": {"type": "integer", "description": "Number of days spent training this session"},
                "gold_per_day": {"type": "integer", "default": 1},
            },
            "required": ["character_id", "skill", "days_spent"],
        },
    },
    {
        "name": "downtime_carousing",
        "description": "Carousing downtime activity. Costs 10gp. Roll on a random event table — might make contacts, hear rumors, get into trouble, or find a windfall.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
            },
            "required": ["character_id"],
        },
    },
    {
        "name": "downtime_recuperate",
        "description": "Recuperate during downtime. Spends 3 days to remove a non-permanent condition and restore full HP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
            },
            "required": ["character_id"],
        },
    },
]

_DEATH_AND_CONTINUITY_TOOLS = [
    {
        "name": "resurrect_character",
        "description": "Resurrect a dead character using a resurrection spell (Revivify, Raise Dead, Resurrection, True Resurrection). Requires appropriate spell slot and material components (gold). Revivify: 300gp, within 1 minute. Raise Dead: 500gp, within 10 days. Resurrection: 1000gp. True Resurrection: 25000gp.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string", "description": "ID of the dead character to resurrect"},
                "spell_name": {"type": "string", "enum": ["revivify", "raise_dead", "resurrection", "true_resurrection"]},
                "caster_id": {"type": "string", "description": "ID of the character casting the spell (for slot/gold deduction). Omit for NPC/scroll casting."},
            },
            "required": ["character_id", "spell_name"],
        },
    },
    {
        "name": "npc_heal",
        "description": "An allied NPC heals or stabilizes a player character during combat. Use when a friendly NPC (e.g. a cleric ally) would logically intervene to help a downed PC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "ID of the character to heal"},
                "amount": {"type": "integer", "description": "HP to restore"},
                "npc_name": {"type": "string", "description": "Name of the NPC providing the healing"},
                "stabilize_only": {"type": "boolean", "default": False, "description": "If true, just stabilize (0 HP but not dying) without healing"},
            },
            "required": ["target_id", "npc_name"],
        },
    },
]

_REPUTATION_TOOLS = [
    {
        "name": "adjust_faction_reputation",
        "description": "Adjust the party's reputation with a faction. Score ranges from -100 (hostile) to +100 (allied). Tiers: hostile (<-50), unfriendly (-50 to -20), neutral (-20 to +20), friendly (+20 to +50), allied (>+50).",
        "input_schema": {
            "type": "object",
            "properties": {
                "faction_id": {"type": "string", "description": "Faction identifier"},
                "delta": {"type": "integer", "description": "Change amount (positive = improve, negative = worsen). Typical: ±5 minor, ±10 significant, ±25 major."},
                "reason": {"type": "string", "description": "Brief reason: 'saved their caravan' or 'stole from the temple'"},
            },
            "required": ["faction_id", "delta", "reason"],
        },
    },
    {
        "name": "get_faction_reputation",
        "description": "Check the party's current reputation with a faction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "faction_id": {"type": "string"},
            },
            "required": ["faction_id"],
        },
    },
]

_TRAVEL_TOOLS = [
    {
        "name": "travel_to_location",
        "description": "Travel from the current location to a connected destination. Calculates travel time, advances the clock, and flags random encounter eligibility. Use instead of set_location when travel time should pass.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_id": {"type": "string", "description": "Target location ID"},
                "pace": {"type": "string", "enum": ["normal", "fast", "slow"], "default": "normal",
                         "description": "Travel pace: fast (×0.75 time, -5 passive Perception), normal, slow (×1.5 time, can stealth)"},
            },
            "required": ["destination_id"],
        },
    },
]

ALL_TOOL_SCHEMAS: list[dict] = (
    _DICE_AND_CHECK_TOOLS + _COMBAT_TOOLS + _STATE_TOOLS
    + _ECONOMY_TOOLS + _DEATH_AND_CONTINUITY_TOOLS
    + _REPUTATION_TOOLS + _TRAVEL_TOOLS
)

# Which tools consume action economy resources
ACTION_COSTS: dict[str, str] = {
    "attack": "action",
    "cast_spell": "variable",  # depends on spell.casting_time
    "apply_condition": "action",
    "death_save": "free",  # death saves happen outside normal turns
    "use_second_wind": "bonus_action",
    "use_lay_on_hands": "action",
}

# Tools that require combat to be active
COMBAT_ONLY_TOOLS = frozenset({
    "attack", "end_turn", "end_combat", "death_save",
})


# ---------------------------------------------------------------------------
# ToolDispatcher
# ---------------------------------------------------------------------------

class ToolDispatcher:
    def __init__(
        self,
        game_state: "GameState",
        event_log: EventLog,
        save_path: str = "saves/autosave.json",
        backend: object = None,
        campaign: object = None,
    ):
        self.game_state = game_state
        self.event_log = event_log
        self.save_path = save_path
        self.backend = backend
        self.campaign = campaign
        self._npc_sessions: dict[str, object] = {}  # npc_id → NPCDialogueSession

        # Wire up journal manager if backend is available
        self._journal_manager = None
        if backend is not None:
            from src.engine.journal_manager import JournalManager
            self._journal_manager = JournalManager(game_state.journal, backend)

    def dispatch(self, tool_name: str, inputs: dict) -> dict:
        """Route tool call to engine with validation."""
        try:
            # Validate action economy in combat
            if self.game_state.combat.active and tool_name in ACTION_COSTS:
                validation = self._validate_combat_action(tool_name, inputs)
                if not validation["valid"]:
                    logger.warning("Action economy rejected: %s — %s", tool_name, validation["reason"])
                    return {"success": False, "error": validation["reason"]}

            result = self._route(tool_name, inputs)
            self.event_log.log(tool_name, inputs, result)
            return result
        except KeyError as e:
            logger.warning("Tool dispatch KeyError: %s(%s) — %s", tool_name, inputs, e)
            return {"success": False, "error": f"Character/object not found: {e}"}
        except Exception as e:
            logger.error("Tool dispatch error: %s(%s) — %s: %s", tool_name, inputs, type(e).__name__, e, exc_info=True)
            return {"success": False, "error": f"Engine error: {type(e).__name__}: {e}"}

    @staticmethod
    def _is_sneak_attack_eligible(attacker, weapon, has_advantage: bool, gs: "GameState") -> bool:
        """Check if a Rogue's Sneak Attack can trigger (simplified 5e).

        Requires finesse or ranged weapon. Triggers with advantage, or when
        another non-unconscious ally is in combat (simplified adjacency).
        """
        props = [p.lower() for p in weapon.properties]
        if "finesse" not in props and "ranged" not in props:
            return False
        if has_advantage:
            return True
        # Simplified adjacency: any other living PC in combat
        if gs.combat.active:
            for pid in gs.player_character_ids:
                if pid != attacker.id:
                    ally = gs.characters.get(pid)
                    if ally and ally.hp > 0 and "unconscious" not in ally.conditions:
                        return True
        return False

    def _validate_combat_action(self, tool_name: str, inputs: dict) -> dict:
        combat = self.game_state.combat
        actor_id = inputs.get("attacker_id") or inputs.get("caster_id") or inputs.get("character_id")
        combatant = combat.combatants.get(actor_id) if actor_id else None

        if not combatant:
            return {"valid": True}  # non-actor tools are fine

        if combatant.character_id != combat.current_combatant_id:
            return {"valid": False, "reason": f"It's not {combatant.character_id}'s turn yet."}

        action_cost = ACTION_COSTS.get(tool_name, "free")
        if action_cost == "action" and not combatant.has_action:
            return {"valid": False, "reason": "No action remaining this turn."}
        if action_cost == "bonus_action" and not combatant.has_bonus_action:
            return {"valid": False, "reason": "No bonus action remaining this turn."}

        return {"valid": True}

    def _route(self, tool_name: str, inputs: dict) -> dict:
        gs = self.game_state

        match tool_name:
            # --- Dice / Checks ---
            case "roll_dice":
                from src.engine.dice import roll_dice
                result = roll_dice(inputs["dice_expr"])
                return {"success": True, "expression": result.expression, "total": result.total,
                        "rolls": result.individual_rolls, "modifier": result.modifier, "reason": inputs.get("reason", "")}

            case "ability_check":
                char = gs.get_character(inputs["character_id"])
                result = ability_check(
                    char, inputs["ability"], inputs["dc"],
                    skill=inputs.get("skill"),
                    advantage=inputs.get("advantage", False),
                    disadvantage=inputs.get("disadvantage", False),
                )
                return {"success": True, **result.model_dump()}

            case "saving_throw":
                char = gs.get_character(inputs["character_id"])
                result = saving_throw(
                    char, inputs["ability"], inputs["dc"],
                    advantage=inputs.get("advantage", False),
                    disadvantage=inputs.get("disadvantage", False),
                )
                return {"success": True, **result.model_dump()}

            # --- Combat ---
            case "start_combat":
                self._npc_sessions.clear()
                participant_ids = list(inputs["participant_ids"])
                # Spawn monster templates if provided
                spawned_ids = []
                for tmpl_id in inputs.get("monster_templates", []):
                    monster = get_monster_template(tmpl_id)
                    # Assign unique ID
                    base = tmpl_id
                    counter = 1
                    mid = f"{base}_{counter}"
                    while mid in gs.characters:
                        counter += 1
                        mid = f"{base}_{counter}"
                    monster.id = mid
                    gs.characters[mid] = monster
                    spawned_ids.append(mid)
                participant_ids.extend(spawned_ids)
                # Deduplicate while preserving order
                seen: set[str] = set()
                unique_ids: list[str] = []
                for pid in participant_ids:
                    if pid not in seen:
                        seen.add(pid)
                        unique_ids.append(pid)
                return combat_engine.start_combat(gs, unique_ids)

            case "attack":
                attacker = gs.get_character(inputs["attacker_id"])
                target = gs.get_character(inputs["target_id"])
                weapon_name = inputs["weapon_name"].lower()
                weapon = next(
                    (w for w in attacker.weapons if w.name.lower() == weapon_name),
                    None,
                )
                if weapon is None:
                    return {"success": False, "error": f"{attacker.name} does not have a weapon named {inputs['weapon_name']!r}."}
                from src.engine.rules import attack_roll as _attack_roll
                has_advantage = inputs.get("advantage", False)
                atk = _attack_roll(
                    attacker, target, weapon,
                    advantage=has_advantage,
                    disadvantage=inputs.get("disadvantage", False),
                )
                result: dict = {
                    "success": True,
                    "attacker": attacker.name,
                    "target": target.name,
                    "roll": atk.roll.individual_rolls,
                    "attack_bonus": atk.attack_bonus,
                    "total_attack": atk.total_attack,
                    "target_ac": atk.target_ac,
                    "hits": atk.hits,
                    "is_crit": atk.is_crit,
                    "is_nat1": atk.is_nat1,
                }
                if atk.hits and atk.damage is not None:
                    total_damage = atk.damage
                    sneak_info = None
                    # Sneak Attack (Rogue): extra damage with finesse/ranged weapons
                    sneak_dice = attacker.class_resources.get("sneak_attack_dice", 0)
                    if sneak_dice > 0 and self._is_sneak_attack_eligible(
                        attacker, weapon, has_advantage, gs
                    ):
                        from src.engine.dice import roll_dice as _roll_sneak
                        sneak_roll = _roll_sneak(f"{sneak_dice}d6")
                        sneak_dmg = sneak_roll.total
                        if atk.is_crit:
                            sneak_dmg += _roll_sneak(f"{sneak_dice}d6").total
                        total_damage += sneak_dmg
                        sneak_info = {"dice": f"{sneak_dice}d6", "damage": sneak_dmg}
                    dmg_result = apply_damage(target, total_damage, atk.damage_type or "slashing")
                    result["damage"] = total_damage
                    result["damage_type"] = atk.damage_type
                    result["hp_remaining"] = target.hp
                    if sneak_info:
                        result["sneak_attack"] = sneak_info
                    result.update({k: v for k, v in dmg_result.items() if k not in result})
                # Consume action
                if gs.combat.active:
                    gs.combat.consume_action(inputs["attacker_id"])
                return result

            case "cast_spell":
                caster = gs.get_character(inputs["caster_id"])
                spell = get_spell(inputs["spell_name"])
                if spell is None:
                    return {"success": False, "error": f"Spell {inputs['spell_name']!r} not found in SRD data."}
                # Validate caster knows this spell (skip for monsters / characters with empty spell list)
                if caster.is_player and caster.known_spells:
                    spell_name_lower = inputs["spell_name"].lower()
                    known_lower = [s.lower() for s in caster.known_spells]
                    if spell_name_lower not in known_lower:
                        return {
                            "success": False,
                            "error": f"{caster.name} does not know {inputs['spell_name']!r}. "
                                     f"Known spells: {', '.join(caster.known_spells)}",
                        }
                targets = [gs.get_character(tid) for tid in inputs.get("target_ids", [])]
                cast_level = inputs.get("spell_level", spell.level)
                result = resolve_spell(gs, spell, caster, targets, cast_level)
                # Consume action/bonus based on spell's casting_time
                if gs.combat.active and result.get("success"):
                    if spell.casting_time == "action":
                        gs.combat.consume_action(inputs["caster_id"])
                    elif spell.casting_time == "bonus_action":
                        gs.combat.consume_bonus_action(inputs["caster_id"])
                return result

            case "apply_damage":
                target = gs.get_character(inputs["target_id"])
                return apply_damage(target, inputs["amount"], inputs["damage_type"])

            case "apply_healing":
                target = gs.get_character(inputs["target_id"])
                return apply_healing(target, inputs["amount"])

            case "apply_condition":
                target = gs.get_character(inputs["target_id"])
                duration = inputs.get("duration_rounds")
                combat = gs.combat if gs.combat.active else None
                return apply_condition(target, inputs["condition"], duration, combat_state=combat)

            case "remove_condition":
                target = gs.get_character(inputs["target_id"])
                combat = gs.combat if gs.combat.active else None
                return remove_condition(target, inputs["condition"], combat_state=combat)

            case "get_monster_actions":
                return gs.get_monster_actions(inputs["monster_id"])

            case "death_save":
                return combat_engine.death_save(gs, inputs["character_id"])

            case "end_turn":
                return combat_engine.end_turn(gs)

            case "end_combat":
                return combat_engine.end_combat(gs, inputs["xp_awarded"])

            case "use_legendary_action":
                from src.models.monster import Monster as _Monster
                monster = gs.get_character(inputs["monster_id"])
                if not isinstance(monster, _Monster):
                    return {"success": False, "error": f"{inputs['monster_id']} is not a monster."}
                if monster.legendary_actions_remaining <= 0:
                    return {"success": False, "error": f"{monster.name} has no legendary actions remaining this round."}
                action_name = inputs["action_name"].lower()
                action = next((a for a in monster.legendary_actions if a.name.lower() == action_name), None)
                if action is None:
                    available = [a.name for a in monster.legendary_actions]
                    return {"success": False, "error": f"Unknown legendary action. Available: {available}"}
                if action.cost > monster.legendary_actions_remaining:
                    return {"success": False, "error": f"{action.name} costs {action.cost} uses but only {monster.legendary_actions_remaining} remaining."}
                monster.legendary_actions_remaining -= action.cost
                return {
                    "success": True,
                    "monster": monster.name,
                    "action": action.name,
                    "description": action.description,
                    "remaining": monster.legendary_actions_remaining,
                }

            case "use_legendary_resistance":
                from src.models.monster import Monster as _Monster2
                monster = gs.get_character(inputs["monster_id"])
                if not isinstance(monster, _Monster2):
                    return {"success": False, "error": f"{inputs['monster_id']} is not a monster."}
                if monster.legendary_resistances_remaining <= 0:
                    return {"success": False, "error": f"{monster.name} has no legendary resistances remaining."}
                monster.legendary_resistances_remaining -= 1
                return {
                    "success": True,
                    "monster": monster.name,
                    "remaining": monster.legendary_resistances_remaining,
                    "note": f"{monster.name} chooses to succeed on the saving throw.",
                }

            # --- State management ---
            case "get_character_sheet":
                return gs.get_character_sheet(inputs["character_id"])

            case "take_short_rest":
                if gs.combat.active:
                    return {"success": False, "error": "Cannot take a short rest during combat."}
                char = gs.get_character(inputs["character_id"])
                return rest_engine.short_rest(char, inputs["hit_dice_to_spend"])

            case "take_long_rest":
                if gs.combat.active:
                    return {"success": False, "error": "Cannot take a long rest during combat."}
                char = gs.get_character(inputs["character_id"])
                return rest_engine.long_rest(char)

            case "add_item":
                return gs.add_item(
                    inputs["character_id"], inputs["item_name"],
                    quantity=inputs.get("quantity", 1),
                    weight=inputs.get("weight", 0.0),
                    description=inputs.get("description", ""),
                )

            case "remove_item":
                return gs.remove_item(inputs["character_id"], inputs["item_name"], inputs.get("quantity", 1))

            case "award_xp":
                return gs.award_xp(inputs["character_ids"], inputs["xp"])

            case "update_quest":
                return gs.update_quest(
                    inputs["quest_id"],
                    completed_objective=inputs.get("completed_objective"),
                    new_status=inputs.get("new_status"),
                )

            case "set_location":
                self._npc_sessions.clear()
                return gs.set_location(inputs["location_id"])

            case "query_world_lore":
                if gs.campaign is None:
                    return {"success": False, "error": "No campaign loaded."}
                return gs.campaign.query(inputs["query_type"], inputs["id"])

            case "save_game":
                gs.save(self.save_path)
                return {"success": True, "path": str(self.save_path)}

            case "improve_ability_score":
                char = gs.get_character(inputs["character_id"])
                ability, delta = inputs["ability"], inputs["increase_by"]
                new_val = min(20, getattr(char.ability_scores, ability) + delta)
                setattr(char.ability_scores, ability, new_val)
                # Recalculate AC if an AC-relevant ability changed
                from src.engine.rules import recalculate_ac
                old_ac = char.ac
                char.ac = recalculate_ac(char)
                result = {
                    "success": True,
                    "character": char.name,
                    "ability": ability,
                    "new_score": new_val,
                }
                if char.ac != old_ac:
                    result["ac_changed"] = f"{old_ac} → {char.ac}"
                return result

            case "use_action_surge":
                char = gs.get_character(inputs["character_id"])
                if not char.is_player:
                    return {"success": False, "error": "Only player characters can use Action Surge."}
                charges = char.class_resources.get("action_surge", 0)
                if charges <= 0:
                    return {"success": False, "error": f"{char.name} has no Action Surge charges."}
                char.class_resources["action_surge"] = charges - 1
                if gs.combat.active and inputs["character_id"] in gs.combat.combatants:
                    gs.combat.combatants[inputs["character_id"]].has_action = True
                return {
                    "success": True,
                    "character": char.name,
                    "remaining_charges": char.class_resources["action_surge"],
                    "note": f"{char.name} surges with renewed vigor — an additional action this turn!",
                }

            case "use_second_wind":
                char = gs.get_character(inputs["character_id"])
                if char.class_name != "Fighter":
                    return {"success": False, "error": "Only Fighters can use Second Wind."}
                result = use_second_wind(char)
                if result["success"] and gs.combat.active and inputs["character_id"] in gs.combat.combatants:
                    gs.combat.consume_bonus_action(inputs["character_id"])
                return result

            case "use_lay_on_hands":
                char = gs.get_character(inputs["character_id"])
                if char.class_name != "Paladin":
                    return {"success": False, "error": "Only Paladins can use Lay on Hands."}
                target = gs.get_character(inputs["target_id"])
                result = use_lay_on_hands(char, target, inputs["amount"])
                if result["success"] and gs.combat.active:
                    gs.combat.consume_action(inputs["character_id"])
                return result

            case "learn_spell":
                char = gs.get_character(inputs["character_id"])
                max_level = max(char.max_spell_slots.keys(), default=0)
                from src.engine.progression import learn_spell as _learn_spell
                return _learn_spell(char, inputs["spell_name"], max_level)

            case "get_random_encounter":
                import random as _random
                loc_id = inputs.get("location_id", gs.world.current_location_id)
                if gs.campaign is None:
                    return {"success": False, "error": "No campaign loaded."}
                encounters = gs.campaign.encounter_tables.get(loc_id, [])
                if not encounters:
                    return {"success": False, "error": f"No encounter table for {loc_id!r}."}
                random_encounters = [e for e in encounters if e.trigger == "random"]
                if not random_encounters:
                    return {"success": False, "error": "No random encounters available."}
                encounter = _random.choice(random_encounters)
                return {
                    "success": True,
                    "description": encounter.description,
                    "monster_ids": encounter.monster_ids,
                    "difficulty": encounter.difficulty,
                    "note": "Call start_combat() with these monster_ids in monster_templates to begin.",
                }

            case "lookup_srd":
                return _lookup_srd(inputs["category"], inputs["query"])

            case "search_srd":
                from src.data.srd_client import search_srd as _search_srd
                results = _search_srd(inputs["category"], inputs.get("query", ""))
                return {"success": True, "count": len(results), "results": results}

            case "record_event":
                loc = inputs.get("location_id", gs.world.current_location_id)
                if self._journal_manager:
                    return self._journal_manager.record_event(
                        event=inputs["event"],
                        location_id=loc,
                        involved_npcs=inputs.get("involved_npcs"),
                        importance=inputs.get("importance", "minor"),
                    )
                return {"success": False, "error": "Journal not available."}

            case "update_npc_attitude":
                if self._journal_manager:
                    return self._journal_manager.update_npc_attitude(
                        npc_id=inputs["npc_id"],
                        disposition=inputs["disposition"],
                        notes=inputs.get("notes", ""),
                    )
                return {"success": False, "error": "Journal not available."}

            case "set_world_flag":
                if self._journal_manager:
                    return self._journal_manager.set_world_flag(
                        flag=inputs["flag"],
                        value=inputs.get("value", "true"),
                    )
                return {"success": False, "error": "Journal not available."}

            case "recall_events":
                if self._journal_manager:
                    return self._journal_manager.recall_events(
                        query_type=inputs["query_type"],
                        query_id=inputs.get("query_id", ""),
                        limit=inputs.get("limit", 10),
                    )
                return {"success": False, "error": "Journal not available."}

            case "start_npc_dialogue":
                npc_id = inputs["npc_id"]
                if gs.campaign is None:
                    return {"success": False, "error": "No campaign loaded."}
                if self.backend is None:
                    return {"success": False, "error": "No LLM backend available for NPC dialogue."}
                npc = gs.campaign.get_npc(npc_id)
                if npc is None:
                    # Try fuzzy match before failing
                    valid_ids = list(gs.campaign.key_npcs.keys())
                    matched = gs.campaign._fuzzy_match_id(npc_id, valid_ids)
                    if matched:
                        npc = gs.campaign.get_npc(matched)
                        npc_id = matched
                if npc is None:
                    valid_ids = list(gs.campaign.key_npcs.keys())
                    ids_str = ", ".join(sorted(valid_ids)) if valid_ids else "(none)"
                    return {"success": False, "error": f"NPC {npc_id!r} not found. Valid NPC IDs: {ids_str}"}
                from src.dm.npc_dialogue import NPCDialogueSession
                session = NPCDialogueSession(
                    npc=npc, backend=self.backend, campaign=gs.campaign,
                    journal=gs.journal,
                )
                self._npc_sessions[npc_id] = session
                response = session.respond(
                    inputs["player_input"],
                    context=inputs.get("context", ""),
                )
                return {"success": True, "npc": npc.name, "response": response}

            case "continue_npc_dialogue":
                npc_id = inputs["npc_id"]
                session = self._npc_sessions.get(npc_id)
                if session is None:
                    return {"success": False, "error": f"No active dialogue with {npc_id!r}. Call start_npc_dialogue first."}
                response = session.respond(inputs["player_input"])
                return {"success": True, "npc_id": npc_id, "response": response}

            case "get_location_treasure":
                loc_id = inputs.get("location_id", gs.world.current_location_id)
                loc = gs.world.locations.get(loc_id)
                if not loc:
                    return {"success": False, "error": f"Unknown location: {loc_id!r}"}
                include_found = inputs.get("include_found", False)
                items = []
                for t in loc.treasure:
                    if t.found and not include_found:
                        continue
                    items.append({
                        "name": t.name,
                        "description": t.description,
                        "item_type": t.item_type,
                        "rarity": t.rarity,
                        "bonus": t.bonus,
                        "discovery": t.discovery,
                        "found": t.found,
                        "requires_attunement": t.requires_attunement,
                    })
                return {"success": True, "location": loc.name, "treasure": items, "count": len(items)}

            case "claim_treasure":
                loc_id = inputs.get("location_id", gs.world.current_location_id)
                loc = gs.world.locations.get(loc_id)
                if not loc:
                    return {"success": False, "error": f"Unknown location: {loc_id!r}"}
                item_name = inputs["item_name"]
                for t in loc.treasure:
                    if t.name.lower() == item_name.lower() and not t.found:
                        t.found = True
                        # Add to character's inventory
                        result = gs.add_item(
                            inputs["character_id"], t.name,
                            weight=t.weight, description=t.description,
                        )
                        result["rarity"] = t.rarity
                        result["item_type"] = t.item_type
                        if t.bonus:
                            result["bonus"] = t.bonus
                        if t.requires_attunement:
                            result["requires_attunement"] = True
                            result["note"] = f"Requires attunement. Call attune_item() during a short rest."
                        if t.value_gp:
                            result["value_gp"] = t.value_gp
                        return result
                return {"success": False, "error": f"No unclaimed treasure {item_name!r} at {loc.name}."}

            case "advance_time":
                from src.engine.time_tracking import advance_time as _advance_time
                return _advance_time(
                    gs.world.time,
                    hours=inputs.get("hours", 0),
                    minutes=inputs.get("minutes", 0),
                    game_state=gs,
                )

            case "attune_item":
                char = gs.get_character(inputs["character_id"])
                from src.models.character import MagicItem
                requires = inputs.get("requires_attunement", True)
                if requires and len(char.attuned_items) >= 3:
                    return {
                        "success": False,
                        "error": f"{char.name} already has 3 attuned items (max). Unattune one first.",
                        "attuned": [mi.name for mi in char.attuned_items],
                    }
                # Check for duplicate attunement
                item_name = inputs["item_name"]
                if any(mi.name.lower() == item_name.lower() for mi in char.attuned_items):
                    return {"success": False, "error": f"{char.name} is already attuned to {item_name!r}."}
                magic_item = MagicItem(
                    name=item_name,
                    item_type=inputs["item_type"],
                    bonus=inputs.get("bonus", 0),
                    rarity=inputs.get("rarity", "uncommon"),
                    requires_attunement=requires,
                    properties=inputs.get("properties", {}),
                    description=inputs.get("description", ""),
                )
                char.attuned_items.append(magic_item)
                result = {
                    "success": True,
                    "character": char.name,
                    "item": magic_item.name,
                    "bonus": magic_item.bonus,
                    "slots_used": len(char.attuned_items),
                    "slots_remaining": 3 - len(char.attuned_items),
                }
                # Note: magic item AC bonuses are applied at attack-resolution
                # time, not baked into char.ac, to avoid double-stacking.
                return result

            case "unattune_item":
                char = gs.get_character(inputs["character_id"])
                item_name = inputs["item_name"]
                for i, mi in enumerate(char.attuned_items):
                    if mi.name.lower() == item_name.lower():
                        char.attuned_items.pop(i)
                        return {
                            "success": True,
                            "character": char.name,
                            "removed": item_name,
                            "slots_used": len(char.attuned_items),
                            "slots_remaining": 3 - len(char.attuned_items),
                        }
                return {"success": False, "error": f"{char.name} is not attuned to {item_name!r}."}

            case "equip_armor":
                char = gs.get_character(inputs["character_id"])
                from src.engine.rules import recalculate_ac
                from src.models.character import Armor as ArmorModel
                item_name = inputs["item_name"]

                if item_name.lower() == "unequip":
                    # Just remove current armor
                    if char.armor is None:
                        return {"success": False, "error": f"{char.name} has no armor equipped."}
                    old_armor = char.armor
                    # Return old armor to inventory
                    gs.add_item(inputs["character_id"], old_armor.name)
                    char.armor = None
                    char.ac = recalculate_ac(char)
                    return {
                        "success": True,
                        "character": char.name,
                        "unequipped": old_armor.name,
                        "new_ac": char.ac,
                    }

                # Equip new armor — need base_ac and armor_type
                if "base_ac" not in inputs or "armor_type" not in inputs:
                    return {
                        "success": False,
                        "error": "Must provide base_ac and armor_type when equipping armor.",
                    }

                # Remove from inventory if present
                inv_match = next(
                    (it for it in char.inventory if it.name.lower() == item_name.lower()),
                    None,
                )
                if inv_match:
                    gs.remove_item(inputs["character_id"], inv_match.name, 1)

                # Return old armor to inventory
                old_armor_name = None
                if char.armor:
                    old_armor_name = char.armor.name
                    gs.add_item(inputs["character_id"], char.armor.name)

                char.armor = ArmorModel(
                    name=item_name,
                    base_ac=inputs["base_ac"],
                    armor_type=inputs["armor_type"],
                    stealth_disadvantage=inputs.get("stealth_disadvantage", False),
                    strength_requirement=inputs.get("strength_requirement"),
                )
                old_ac = char.ac
                char.ac = recalculate_ac(char)
                result = {
                    "success": True,
                    "character": char.name,
                    "equipped": item_name,
                    "old_ac": old_ac,
                    "new_ac": char.ac,
                }
                if old_armor_name:
                    result["returned_to_inventory"] = old_armor_name
                return result

            case "equip_shield":
                char = gs.get_character(inputs["character_id"])
                from src.engine.rules import recalculate_ac
                equip = inputs["equip"]
                if equip and char.shield:
                    return {"success": False, "error": f"{char.name} already has a shield equipped."}
                if not equip and not char.shield:
                    return {"success": False, "error": f"{char.name} has no shield equipped."}
                old_ac = char.ac
                char.shield = equip
                char.ac = recalculate_ac(char)
                action = "equipped" if equip else "unequipped"
                return {
                    "success": True,
                    "character": char.name,
                    "shield": action,
                    "old_ac": old_ac,
                    "new_ac": char.ac,
                }

            case "equip_weapon":
                char = gs.get_character(inputs["character_id"])
                from src.models.character import Weapon as WeaponModel
                weapon_name = inputs["weapon_name"]
                # Check if already equipped
                if any(w.name.lower() == weapon_name.lower() for w in char.weapons):
                    return {"success": False, "error": f"{char.name} already has {weapon_name!r} equipped."}
                # Remove from inventory if present
                inv_match = next(
                    (it for it in char.inventory if it.name.lower() == weapon_name.lower()),
                    None,
                )
                if inv_match:
                    gs.remove_item(inputs["character_id"], inv_match.name, 1)
                weapon = WeaponModel(
                    name=weapon_name,
                    damage_dice=inputs["damage_dice"],
                    damage_type=inputs["damage_type"],
                    properties=inputs.get("properties", []),
                    range_normal=inputs.get("range_normal"),
                    range_long=inputs.get("range_long"),
                )
                char.weapons.append(weapon)
                return {
                    "success": True,
                    "character": char.name,
                    "equipped": weapon_name,
                    "damage": f"{weapon.damage_dice} {weapon.damage_type}",
                    "weapons": [w.name for w in char.weapons],
                }

            case "unequip_weapon":
                char = gs.get_character(inputs["character_id"])
                weapon_name = inputs["weapon_name"]
                for i, w in enumerate(char.weapons):
                    if w.name.lower() == weapon_name.lower():
                        char.weapons.pop(i)
                        gs.add_item(inputs["character_id"], weapon_name)
                        return {
                            "success": True,
                            "character": char.name,
                            "unequipped": weapon_name,
                            "weapons": [w.name for w in char.weapons],
                        }
                return {
                    "success": False,
                    "error": f"{char.name} has no weapon {weapon_name!r} equipped.",
                    "equipped_weapons": [w.name for w in char.weapons],
                }

            # --- Economy ---
            case "buy_item":
                from src.engine.economy import buy_item as _buy_item
                char = gs.get_character(inputs["character_id"])
                return _buy_item(
                    char, inputs["item_name"], inputs["price"],
                    quantity=inputs.get("quantity", 1),
                    weight=inputs.get("weight", 0.0),
                    description=inputs.get("description", ""),
                )

            case "sell_item":
                from src.engine.economy import sell_item as _sell_item
                char = gs.get_character(inputs["character_id"])
                return _sell_item(
                    char, inputs["item_name"], inputs["price"],
                    quantity=inputs.get("quantity", 1),
                )

            case "get_item_price":
                from src.engine.economy import get_item_price as _get_price
                price = _get_price(inputs["item_name"], inputs.get("rarity", "common"))
                if price is not None:
                    return {"success": True, "item": inputs["item_name"], "price_gp": price}
                return {
                    "success": True,
                    "item": inputs["item_name"],
                    "price_gp": None,
                    "note": "Item not in price database. Set a fair price based on rarity and utility.",
                }

            case "craft_item":
                from src.engine.economy import craft_item as _craft_item
                char = gs.get_character(inputs["character_id"])
                return _craft_item(
                    char, inputs["item_name"],
                    rarity=inputs.get("rarity", "common"),
                    tool_proficiency=inputs.get("tool_proficiency"),
                    material_cost=inputs.get("material_cost"),
                )

            case "downtime_training":
                from src.engine.economy import downtime_training as _training
                char = gs.get_character(inputs["character_id"])
                return _training(
                    char, inputs["skill"], inputs["days_spent"],
                    gold_per_day=inputs.get("gold_per_day", 1),
                )

            case "downtime_carousing":
                from src.engine.economy import downtime_carousing as _carousing
                char = gs.get_character(inputs["character_id"])
                return _carousing(char)

            case "downtime_recuperate":
                from src.engine.economy import downtime_recuperate as _recuperate
                char = gs.get_character(inputs["character_id"])
                return _recuperate(char)

            # --- Death & Continuity ---
            case "resurrect_character":
                from src.engine.rules import resurrect_character as _resurrect
                target = gs.get_character(inputs["character_id"])
                caster = gs.get_character(inputs["caster_id"]) if inputs.get("caster_id") else None
                return _resurrect(target, inputs["spell_name"], caster=caster)

            case "npc_heal":
                target = gs.get_character(inputs["target_id"])
                npc_name = inputs["npc_name"]
                if inputs.get("stabilize_only"):
                    # Stabilize: set to 0 HP, remove unconscious, reset death saves
                    if "unconscious" in target.conditions:
                        target.death_saves = type(target.death_saves)()
                        return {
                            "success": True,
                            "npc": npc_name,
                            "target": target.name,
                            "stabilized": True,
                            "note": f"{npc_name} stabilizes {target.name}.",
                        }
                    return {"success": False, "error": f"{target.name} is not unconscious."}
                amount = inputs.get("amount", 0)
                if amount <= 0:
                    return {"success": False, "error": "Healing amount must be positive."}
                heal_result = apply_healing(target, amount)
                return {
                    "success": True,
                    "npc": npc_name,
                    "target": target.name,
                    **heal_result,
                }

            # --- Faction Reputation ---
            case "adjust_faction_reputation":
                if self._journal_manager:
                    rep = gs.journal.adjust_faction_reputation(
                        inputs["faction_id"], inputs["delta"], inputs.get("reason", ""),
                    )
                    return {
                        "success": True,
                        "faction_id": inputs["faction_id"],
                        "new_score": rep.score,
                        "tier": rep.tier,
                        "delta": inputs["delta"],
                        "reason": inputs.get("reason", ""),
                    }
                # Fallback: directly adjust on journal
                rep = gs.journal.adjust_faction_reputation(
                    inputs["faction_id"], inputs["delta"], inputs.get("reason", ""),
                )
                return {
                    "success": True,
                    "faction_id": inputs["faction_id"],
                    "new_score": rep.score,
                    "tier": rep.tier,
                }

            case "get_faction_reputation":
                faction_id = inputs["faction_id"]
                rep = gs.journal.faction_reputations.get(faction_id)
                if rep is None:
                    return {
                        "success": True,
                        "faction_id": faction_id,
                        "score": 0,
                        "tier": "neutral",
                        "history": [],
                        "note": "No prior interactions recorded.",
                    }
                return {
                    "success": True,
                    "faction_id": faction_id,
                    "score": rep.score,
                    "tier": rep.tier,
                    "history": rep.history[-10:],
                }

            # --- Travel ---
            case "travel_to_location":
                from src.engine.time_tracking import advance_time as _advance_time
                from src.engine.time_tracking import travel_time as _travel_time
                travel_info = _travel_time(gs, inputs["destination_id"])
                if not travel_info["success"]:
                    return travel_info
                # Apply pace modifier
                hours = travel_info["travel_hours"]
                pace = inputs.get("pace", "normal")
                if pace == "fast":
                    hours *= 0.75
                elif pace == "slow":
                    hours *= 1.5
                # Advance time
                full_hours = int(hours)
                extra_minutes = int((hours - full_hours) * 60)
                if full_hours > 0 or extra_minutes > 0:
                    time_result = _advance_time(
                        gs.world.time, hours=full_hours, minutes=extra_minutes, game_state=gs,
                    )
                    travel_info["time_elapsed"] = time_result
                # Move to destination
                loc_result = gs.set_location(inputs["destination_id"])
                travel_info.update(loc_result)
                travel_info["pace"] = pace
                self._npc_sessions.clear()
                return travel_info

            case _:
                return {"success": False, "error": f"Unknown tool: {tool_name!r}"}
