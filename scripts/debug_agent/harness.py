"""Headless game driver — wraps DungeonMaster without the Rich CLI layer."""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.campaign.loader import load_campaign, load_srd_data
from src.dm.dungeon_master import DungeonMaster
from src.engine.game_state import GameState
from src.log.event_log import EventLog
from src.models.character import AbilityScores, Armor, Character, Weapon
from src.models.world import Location, Quest, WorldState


@dataclass
class TurnResult:
    ok: bool
    narrative: str = ""
    error: str = ""
    traceback: str = ""
    state: dict = field(default_factory=dict)


class HeadlessHarness:
    """Drives the game without any UI. Instantiates GameState + DungeonMaster directly."""

    def __init__(
        self,
        campaign_path: str = "campaigns/shattered_crown.json",
        characters_path: str | None = None,
        provider: str = "deepseek",
        model: str | None = None,
    ) -> None:
        load_srd_data()

        # Load campaign
        cp = Path(campaign_path)
        if not cp.exists():
            cp = cp.with_suffix(".json")
        self.campaign = load_campaign(cp)

        # Load or create characters
        if characters_path and Path(characters_path).exists():
            data = json.loads(Path(characters_path).read_text())
            characters: dict[str, Character] = {}
            pc_ids: list[str] = []
            for char_data in data.get("characters", []):
                char = Character.model_validate(char_data)
                characters[char.id] = char
                if char.is_player:
                    pc_ids.append(char.id)
        else:
            characters, pc_ids = _default_characters()

        # Build game state
        starting_loc = self.campaign.starting_location_id or next(iter(self.campaign.locations))
        world = WorldState(
            current_location_id=starting_loc,
            locations=dict(self.campaign.locations),
            quests=[
                Quest(
                    id=h.id,
                    title=h.title,
                    description=h.description,
                    status="active",
                    objectives=[h.description],
                    rewards=h.rewards,
                )
                for h in self.campaign.plot_hooks[:2]
            ],
        )
        self.game_state = GameState(
            player_character_ids=pc_ids,
            characters=characters,
            world=world,
            campaign=self.campaign,
        )

        self.event_log = EventLog(self.game_state)

        self.dm = DungeonMaster(
            game_state=self.game_state,
            campaign=self.campaign,
            event_log=self.event_log,
            provider=provider,
            model=model,
            save_path="/dev/null",  # no autosave during debug runs
        )

    def step(self, player_input: str, timeout: float = 120.0) -> TurnResult:
        """Execute one game turn. Returns structured result."""
        import signal

        def _timeout_handler(signum: int, frame: Any) -> None:
            raise TimeoutError(f"Turn timed out after {timeout}s")

        # Set timeout (Unix only)
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(int(timeout))

        try:
            narrative = self.dm.process_player_input(player_input)
            signal.alarm(0)
            return TurnResult(ok=True, narrative=narrative, state=self._snapshot())
        except TimeoutError as e:
            signal.alarm(0)
            return TurnResult(
                ok=False,
                error=str(e),
                traceback=traceback.format_exc(),
                state=self._snapshot(),
            )
        except Exception as e:
            signal.alarm(0)
            return TurnResult(
                ok=False,
                error=str(e),
                traceback=traceback.format_exc(),
                state=self._snapshot(),
            )
        finally:
            signal.signal(signal.SIGALRM, old_handler)

    def _snapshot(self) -> dict:
        """Lightweight state snapshot for reports."""
        gs = self.game_state
        hp_summary = {
            c.name: f"{c.hp}/{c.max_hp}"
            for c in gs.characters.values()
            if c.is_player
        }
        return {
            "location": gs.world.current_location_id,
            "combat_active": gs.combat.active,
            "combat_round": gs.combat.round if gs.combat.active else None,
            "hp_summary": hp_summary,
        }

    def brief_state(self) -> str:
        """3-line state summary for the player AI."""
        gs = self.game_state
        hp_parts = [
            f"{c.name}: {c.hp}/{c.max_hp} HP" + (f" [{', '.join(c.conditions)}]" if c.conditions else "")
            for c in gs.characters.values()
            if c.is_player
        ]
        combat_line = (
            f"Combat: round {gs.combat.round}, turn: {gs.combat.current_combatant_id}"
            if gs.combat.active
            else "No combat"
        )
        location = gs.world.locations.get(gs.world.current_location_id)
        loc_name = location.name if location else gs.world.current_location_id
        return f"Location: {loc_name}\n{combat_line}\nParty: {', '.join(hp_parts)}"


def _default_characters() -> tuple[dict[str, Character], list[str]]:
    """Fallback characters for debug runs."""
    fighter = Character(
        id="aldric",
        name="Aldric Stonemantle",
        race="Human",
        class_name="Fighter",
        level=3,
        xp=900,
        ability_scores=AbilityScores(STR=16, DEX=12, CON=14, INT=10, WIS=10, CHA=10),
        hp=28,
        max_hp=28,
        ac=16,
        proficiency_bonus=2,
        skill_proficiencies=["Athletics", "Perception"],
        weapon_proficiencies=["martial", "simple"],
        armor_proficiencies=["light", "medium", "heavy", "shields"],
        saving_throw_proficiencies=["STR", "CON"],
        hit_dice_remaining=3,
        hit_die_type="d10",
        weapons=[Weapon(name="Longsword", damage_dice="1d8", damage_type="slashing")],
        armor=Armor(name="Chain Mail", base_ac=16, armor_type="heavy"),
    )
    wizard = Character(
        id="zara",
        name="Zara Moonwhisper",
        race="Half-Elf",
        class_name="Wizard",
        level=3,
        xp=900,
        ability_scores=AbilityScores(STR=8, DEX=14, CON=12, INT=16, WIS=12, CHA=14),
        hp=19,
        max_hp=19,
        ac=13,
        proficiency_bonus=2,
        skill_proficiencies=["Arcana", "History", "Investigation"],
        weapon_proficiencies=["simple"],
        armor_proficiencies=["light"],
        saving_throw_proficiencies=["INT", "WIS"],
        spell_slots={1: 4, 2: 2},
        max_spell_slots={1: 4, 2: 2},
        spellcasting_ability="INT",
        known_spells=["Fire Bolt", "Magic Missile", "Fireball", "Shield", "Mage Armor"],
        hit_dice_remaining=3,
        hit_die_type="d6",
        weapons=[],
    )
    characters = {"aldric": fighter, "zara": wizard}
    pc_ids = ["aldric", "zara"]
    return characters, pc_ids
