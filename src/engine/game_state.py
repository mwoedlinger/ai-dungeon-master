"""Central game state container."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from src.engine.progression import apply_level_up
from src.engine.rules import xp_for_level
from src.models.character import Character
from src.models.combat import CombatState
from src.models.journal import WorldJournal
from src.models.monster import Monster
from src.models.world import WorldState


@dataclass
class GameState:
    """Central mutable container for all game state."""

    player_character_ids: list[str]
    characters: dict[str, Character]  # includes monsters when active
    world: WorldState
    combat: CombatState = field(default_factory=CombatState)
    journal: WorldJournal = field(default_factory=WorldJournal)
    # Campaign reference injected after construction
    campaign: object = field(default=None, repr=False)

    def get_character(self, character_id: str) -> Character:
        char = self.characters.get(character_id)
        if char is None:
            raise KeyError(f"Character not found: {character_id!r}")
        return char

    @property
    def player_characters(self) -> list[Character]:
        return [self.characters[cid] for cid in self.player_character_ids if cid in self.characters]

    def get_character_sheet(self, character_id: str) -> dict:
        """Full serialized character for the LLM."""
        char = self.get_character(character_id)
        data = char.model_dump()
        # Annotate with spell save DC for convenience
        data["spell_save_dc"] = char.spell_save_dc
        return {"success": True, "character": data}

    def get_monster_actions(self, monster_id: str) -> dict:
        char = self.get_character(monster_id)
        if not isinstance(char, Monster):
            return {"success": False, "error": f"{monster_id} is not a monster."}
        return {
            "success": True,
            "monster": char.name,
            "actions": [a.model_dump() for a in char.actions],
            "special_traits": char.special_traits,
        }

    def add_item(self, character_id: str, item_name: str, quantity: int = 1) -> dict:
        char = self.get_character(character_id)
        for item in char.inventory:
            if item.name.lower() == item_name.lower():
                item.quantity += quantity
                return {"success": True, "item": item_name, "quantity": item.quantity}
        from src.models.character import Item
        char.inventory.append(Item(name=item_name, quantity=quantity))
        return {"success": True, "item": item_name, "quantity": quantity}

    def remove_item(self, character_id: str, item_name: str, quantity: int = 1) -> dict:
        char = self.get_character(character_id)
        for i, item in enumerate(char.inventory):
            if item.name.lower() == item_name.lower():
                if item.quantity < quantity:
                    return {
                        "success": False,
                        "error": f"{char.name} only has {item.quantity} {item_name}.",
                    }
                item.quantity -= quantity
                if item.quantity == 0:
                    char.inventory.pop(i)
                return {"success": True, "item": item_name, "removed": quantity}
        return {"success": False, "error": f"{char.name} does not have {item_name!r}."}

    def update_quest(
        self,
        quest_id: str,
        completed_objective: str | None = None,
        new_status: str | None = None,
    ) -> dict:
        for quest in self.world.quests:
            if quest.id == quest_id:
                if completed_objective and completed_objective not in quest.completed_objectives:
                    quest.completed_objectives.append(completed_objective)
                if new_status:
                    quest.status = new_status  # type: ignore[assignment]
                return {"success": True, "quest": quest.title, "status": quest.status}
        return {"success": False, "error": f"Quest {quest_id!r} not found."}

    def set_location(self, location_id: str) -> dict:
        if location_id not in self.world.locations:
            return {"success": False, "error": f"Unknown location: {location_id!r}"}
        self.world.current_location_id = location_id
        loc = self.world.locations[location_id]
        return {
            "success": True,
            "location": loc.name,
            "description": loc.description,
            "connected_to": loc.connected_to,
        }

    def award_xp(self, character_ids: list[str], xp: int) -> dict:
        """Award XP and check for level-ups."""
        results = []
        for cid in character_ids:
            char = self.characters.get(cid)
            if not char or not char.is_player:
                continue
            char.xp += xp
            level_up_details = []
            while char.level < 20 and char.xp >= xp_for_level(char.level + 1):
                char.level += 1
                level_up_details.append(apply_level_up(char))
            results.append({
                "character": char.name,
                "xp_gained": xp,
                "total_xp": char.xp,
                "level": char.level,
                "leveled_up": bool(level_up_details),
                "level_up_details": level_up_details,
            })
        return {"success": True, "results": results}

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "player_character_ids": self.player_character_ids,
            "characters": {
                cid: char.model_dump()
                for cid, char in self.characters.items()
                if cid in self.player_character_ids
            },
            "world": self.world.model_dump(),
            "combat": self.combat.model_dump(),
            "journal": self.journal.model_dump(),
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: str | Path, campaign=None) -> "GameState":
        data = json.loads(Path(path).read_text())
        characters = {}
        for cid, char_data in data["characters"].items():
            characters[cid] = Character.model_validate(char_data)

        world_data = data["world"]
        world = WorldState.model_validate(world_data)
        combat = CombatState.model_validate(data.get("combat", {}))
        journal = WorldJournal.model_validate(data.get("journal", {}))

        return cls(
            player_character_ids=data["player_character_ids"],
            characters=characters,
            world=world,
            combat=combat,
            journal=journal,
            campaign=campaign,
        )
