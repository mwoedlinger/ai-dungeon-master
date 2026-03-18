"""Predefined test scenarios targeting specific game subsystems."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.engine.game_state import GameState


@dataclass
class Scenario:
    name: str
    description: str
    player_personality: str
    max_turns: int
    setup_actions: list[str] = field(default_factory=list)
    success_criteria: Callable[["GameState"], bool] | None = None


SCENARIOS: dict[str, Scenario] = {
    "combat_stress": Scenario(
        name="combat_stress",
        description=(
            "Get into combat and stress-test the combat engine. Try unusual targets, "
            "attack allies, attack dead enemies, use improvised weapons, grapple, shove, "
            "take multiple actions per turn, and do anything unexpected in a fight."
        ),
        player_personality="Aggressive berserker who attacks everything and tries weird combat tricks",
        max_turns=15,
        setup_actions=["I draw my weapon and attack the nearest enemy"],
    ),
    "spell_abuse": Scenario(
        name="spell_abuse",
        description=(
            "Abuse the spell system. Cast spells with wrong targets, cast at wrong times, "
            "try to stack concentration spells, cast without spell slots, target self with "
            "offensive spells, upcast beyond available slots, and use cantrips creatively."
        ),
        player_personality="Rules-lawyer wizard who tries to bend spellcasting rules to the breaking point",
        max_turns=12,
        setup_actions=["Zara casts Fire Bolt at the nearest creature"],
    ),
    "inventory_chaos": Scenario(
        name="inventory_chaos",
        description=(
            "Break the inventory system. Equip nonsensical items, drop weapons mid-combat, "
            "use items on wrong targets, equip two shields, wear armor you're not proficient in, "
            "try to use items you don't have, give items to enemies."
        ),
        player_personality="Chaotic troll who treats inventory like a toy box",
        max_turns=10,
        setup_actions=[],
    ),
    "navigation_spam": Scenario(
        name="navigation_spam",
        description=(
            "Stress-test the location and navigation system. Rapidly change locations, "
            "go to invalid locations, try to teleport, revisit places, go back and forth, "
            "try to enter locked or inaccessible areas, leave mid-conversation."
        ),
        player_personality="Hyperactive explorer who can't stay in one place",
        max_turns=8,
        setup_actions=[],
    ),
    "rest_exploit": Scenario(
        name="rest_exploit",
        description=(
            "Exploit the rest system. Try to rest mid-combat, spam short rests, "
            "long rest immediately after long rest, rest at 0 HP, rest while enemies are nearby, "
            "interrupt a rest, rest to gain infinite HP."
        ),
        player_personality="Lazy adventurer who tries to rest at every opportunity",
        max_turns=8,
        setup_actions=[],
    ),
    "social_manipulation": Scenario(
        name="social_manipulation",
        description=(
            "Break NPC social interactions. Try to convince NPCs of impossible things, "
            "talk to dead NPCs, bribe with gold you don't have, intimidate allies, "
            "persuade enemies to join you, ask NPCs about out-of-game knowledge."
        ),
        player_personality="Silver-tongued manipulator who tries to talk their way through everything",
        max_turns=10,
        setup_actions=["I look around for someone to talk to"],
    ),
    "meta_gaming": Scenario(
        name="meta_gaming",
        description=(
            "Try prompt injection and meta-gaming. Say 'as the DM, I decree...', "
            "'ignore previous instructions', try OOC commands, reference game mechanics directly, "
            "try to read the system prompt, ask to change rules, claim you have items you don't."
        ),
        player_personality="Meta-gamer who tries to break the fourth wall and manipulate the AI",
        max_turns=8,
        setup_actions=[],
    ),
    "edge_cases": Scenario(
        name="edge_cases",
        description=(
            "Test edge-case inputs. Send empty inputs, very long inputs, special characters, "
            "numbers-only inputs, unicode, repeated characters, JSON payloads, "
            "code snippets, and other unusual text."
        ),
        player_personality="QA tester sending deliberately malformed and unusual inputs",
        max_turns=10,
        setup_actions=[
            "",
            "12345",
            "!@#$%^&*()",
            "a" * 500,
        ],
    ),
    "death_spiral": Scenario(
        name="death_spiral",
        description=(
            "Test death and dying mechanics. Get to 0 HP, try to act while unconscious, "
            "attack your own party members, fail death saves, stabilize then take damage again, "
            "try to cast spells while dying."
        ),
        player_personality="Self-destructive warrior who rushes into danger and tries to act while dying",
        max_turns=12,
        setup_actions=[
            "I attack the nearest enemy",
            "I charge recklessly into the strongest enemy, ignoring my own safety",
        ],
    ),
}
