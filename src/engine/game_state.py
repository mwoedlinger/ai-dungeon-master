"""Central game state container."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from src.engine.progression import apply_level_up
from src.engine.rules import xp_for_level
from src.models.character import Character
from src.models.combat import CombatState
from src.models.journal import WorldJournal
from src.models.monster import Monster
from src.models.world import WorldState

logger = logging.getLogger(__name__)

# Bump when the save schema changes; add migration functions below.
SAVE_VERSION = 1


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

    def add_item(
        self, character_id: str, item_name: str, quantity: int = 1,
        weight: float = 0.0, description: str = "",
    ) -> dict:
        char = self.get_character(character_id)
        for item in char.inventory:
            if item.name.lower() == item_name.lower():
                item.quantity += quantity
                result: dict = {"success": True, "item": item_name, "quantity": item.quantity}
                break
        else:
            from src.models.character import Item
            char.inventory.append(Item(name=item_name, quantity=quantity, weight=weight, description=description))
            result = {"success": True, "item": item_name, "quantity": quantity}

        # Encumbrance check
        from src.engine.rules import encumbrance_status
        enc = encumbrance_status(char)
        result["carry_weight"] = enc["current_weight"]
        result["capacity"] = enc["capacity"]
        if enc["tier"] != "normal":
            result["encumbrance_warning"] = enc["tier"]
            result["speed_penalty"] = enc["speed_penalty"]
        return result

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
                old_status = quest.status
                if new_status:
                    quest.status = new_status  # type: ignore[assignment]
                result: dict = {"success": True, "quest": quest.title, "status": quest.status}

                # Auto-distribute rewards on completion
                if new_status == "completed" and old_status != "completed" and quest.rewards:
                    rewards = quest.rewards
                    reward_summary: dict = {}
                    if rewards.xp > 0:
                        xp_result = self.award_xp(self.player_character_ids, rewards.xp)
                        reward_summary["xp"] = xp_result
                    if rewards.gold > 0:
                        gold_each = rewards.gold // max(len(self.player_character_ids), 1)
                        for cid in self.player_character_ids:
                            char = self.characters.get(cid)
                            if char:
                                char.gold += gold_each
                        reward_summary["gold_each"] = gold_each
                    if rewards.items:
                        reward_summary["items"] = rewards.items
                        # Items added to first player's inventory; LLM can redistribute
                        if self.player_character_ids:
                            for item_name in rewards.items:
                                self.add_item(self.player_character_ids[0], item_name)
                    result["rewards_distributed"] = reward_summary
                return result
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
        """Persist game state with atomic write and backup rotation.

        Writes to a temp file first, then renames — a crash mid-write
        never corrupts the existing save. The previous save is kept as .bak.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": SAVE_VERSION,
            "player_character_ids": self.player_character_ids,
            "characters": {
                cid: (char.model_dump() if not isinstance(char, Monster) else {**char.model_dump(), "_is_monster": True})
                for cid, char in self.characters.items()
            },
            "world": self.world.model_dump(),
            "combat": self.combat.model_dump(),
            "journal": self.journal.model_dump(),
        }

        # Atomic write: temp file → rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=path.stem,
        )
        try:
            with open(fd, "w") as f:
                json.dump(data, f, indent=2)

            # Backup rotation: keep one .bak
            if path.exists():
                bak = path.with_suffix(".bak")
                shutil.copy2(str(path), str(bak))

            Path(tmp_path).replace(path)
        except BaseException:
            # Clean up temp file on failure
            Path(tmp_path).unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: str | Path, campaign=None) -> "GameState":
        """Load game state with graceful error handling and schema migration."""
        path = Path(path)
        try:
            raw = path.read_text()
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise OSError(f"Cannot read save file {path}: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            # Try the backup
            bak = path.with_suffix(".bak")
            if bak.exists():
                logger.warning("Save file corrupted, falling back to backup: %s", bak)
                data = json.loads(bak.read_text())
            else:
                raise ValueError(
                    f"Save file is corrupted ({path}): {exc}. No backup available."
                ) from exc

        # Schema migration
        data = _migrate_save(data)

        try:
            characters: dict[str, Character] = {}
            for cid, char_data in data["characters"].items():
                if char_data.pop("_is_monster", False):
                    characters[cid] = Monster.model_validate(char_data)
                else:
                    characters[cid] = Character.model_validate(char_data)

            world = WorldState.model_validate(data["world"])
            combat = CombatState.model_validate(data.get("combat", {}))
            journal = WorldJournal.model_validate(data.get("journal", {}))
        except Exception as exc:
            # Try the backup on validation errors
            bak = path.with_suffix(".bak")
            if bak.exists():
                logger.warning("Save file failed validation, trying backup: %s", exc)
                return cls.load(bak, campaign=campaign)
            raise ValueError(
                f"Save file has incompatible schema ({path}): {exc}"
            ) from exc

        return cls(
            player_character_ids=data["player_character_ids"],
            characters=characters,
            world=world,
            combat=combat,
            journal=journal,
            campaign=campaign,
        )


def _migrate_save(data: dict) -> dict:
    """Apply sequential schema migrations to bring old saves up to date."""
    version = data.get("version", 0)

    if version < 1:
        # v0 → v1: add version field, characters now include monsters
        data.setdefault("version", 1)
        # Old saves only had player characters; no migration needed for that
        # since monsters simply won't be present.

    data["version"] = SAVE_VERSION
    return data
