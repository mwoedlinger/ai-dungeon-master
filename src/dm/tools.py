"""Tool schemas, action costs, and ToolDispatcher."""
from __future__ import annotations

from typing import TYPE_CHECKING

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
        "description": "Add an item to a character's inventory.",
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
        "description": "Move the party to a new location. Returns location description.",
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
        "description": "Look up any D&D 5e SRD data: monsters, spells, equipment, classes, races, conditions, skills. Use to get stats before spawning a monster, check spell details, or look up equipment properties.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["monsters", "spells", "equipment", "classes", "races", "conditions", "skills", "features"],
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
                    "enum": ["monsters", "spells", "equipment", "classes", "races", "conditions", "skills"],
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
        "description": "Set a world state flag for tracking branching state. Use for binary or simple state changes that affect future events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "flag": {"type": "string", "description": "Snake_case flag name: 'bridge_destroyed', 'moras_secret_revealed'"},
                "value": {"type": "string", "default": "true"},
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
]

ALL_TOOL_SCHEMAS: list[dict] = _DICE_AND_CHECK_TOOLS + _COMBAT_TOOLS + _STATE_TOOLS

# Which tools consume action economy resources
ACTION_COSTS: dict[str, str] = {
    "attack": "action",
    "cast_spell": "variable",  # depends on spell.casting_time
    "apply_condition": "action",
    "death_save": "free",  # death saves happen outside normal turns
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
                    return {"success": False, "error": validation["reason"]}

            result = self._route(tool_name, inputs)
            self.event_log.log(tool_name, inputs, result)
            return result
        except KeyError as e:
            return {"success": False, "error": f"Character/object not found: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Engine error: {type(e).__name__}: {e}"}

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
                atk = _attack_roll(
                    attacker, target, weapon,
                    advantage=inputs.get("advantage", False),
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
                    dmg_result = apply_damage(target, atk.damage, atk.damage_type or "slashing")
                    result["damage"] = atk.damage
                    result["damage_type"] = atk.damage_type
                    result["hp_remaining"] = target.hp
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
                result = apply_condition(target, inputs["condition"], duration)
                # Track duration on combatant if in combat
                if gs.combat.active and inputs["target_id"] in gs.combat.combatants and duration:
                    gs.combat.combatants[inputs["target_id"]].condition_durations[inputs["condition"]] = duration
                return result

            case "remove_condition":
                target = gs.get_character(inputs["target_id"])
                return remove_condition(target, inputs["condition"])

            case "get_monster_actions":
                return gs.get_monster_actions(inputs["monster_id"])

            case "death_save":
                return combat_engine.death_save(gs, inputs["character_id"])

            case "end_turn":
                return combat_engine.end_turn(gs)

            case "end_combat":
                return combat_engine.end_combat(gs, inputs["xp_awarded"])

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
                return gs.add_item(inputs["character_id"], inputs["item_name"], inputs.get("quantity", 1))

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
                return {
                    "success": True,
                    "character": char.name,
                    "ability": ability,
                    "new_score": new_val,
                }

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
                    return {"success": False, "error": f"NPC {npc_id!r} not found."}
                from src.dm.npc_dialogue import NPCDialogueSession
                session = NPCDialogueSession(npc=npc, backend=self.backend, campaign=gs.campaign)
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

            case _:
                return {"success": False, "error": f"Unknown tool: {tool_name!r}"}
