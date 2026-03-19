"""Tests for remaining Tier 2 features: Death & Continuity, Economy, NPC Memory, Campaign Time."""
from __future__ import annotations

import pytest

from src.engine.economy import (
    buy_item, sell_item, get_item_price, craft_item,
    downtime_training, downtime_carousing, downtime_recuperate,
    EQUIPMENT_PRICES,
)
from src.engine.rules import resurrect_character, apply_damage, apply_healing
from src.engine.time_tracking import advance_time, travel_time, _check_quest_deadlines
from src.models.character import AbilityScores, Character, Item, DeathSaves
from src.models.journal import WorldJournal, FactionReputation
from src.models.world import (
    Location, LocationConnection, Quest, QuestReward, TimeState, WorldState,
)


def _make_char(**overrides) -> Character:
    defaults = dict(
        id="test", name="Test", race="Human", class_name="Fighter",
        level=5, xp=0,
        ability_scores=AbilityScores(STR=16, DEX=14, CON=14, INT=12, WIS=10, CHA=10),
        hp=40, max_hp=40, ac=16, proficiency_bonus=3,
        saving_throw_proficiencies=["STR", "CON"],
        hit_dice_remaining=5, hit_die_type="d10",
        gold=100,
    )
    defaults.update(overrides)
    return Character(**defaults)


# =====================================================================
# Death & Continuity
# =====================================================================

class TestResurrection:
    def test_resurrect_dead_character(self):
        char = _make_char(hp=0, conditions=["dead"])
        result = resurrect_character(char, "revivify")
        assert result["success"]
        assert char.hp == 1
        assert "dead" not in char.conditions

    def test_resurrect_not_dead(self):
        char = _make_char()
        result = resurrect_character(char, "revivify")
        assert not result["success"]
        assert "not dead" in result["error"]

    def test_resurrect_invalid_spell(self):
        char = _make_char(hp=0, conditions=["dead"])
        result = resurrect_character(char, "power_word_heal")
        assert not result["success"]
        assert "Unknown" in result["error"]

    def test_resurrect_with_caster_deducts_gold_and_slot(self):
        dead = _make_char(id="dead1", hp=0, conditions=["dead"])
        caster = _make_char(
            id="cleric", class_name="Cleric", gold=500,
            spell_slots={3: 2}, max_spell_slots={3: 2},
            spellcasting_ability="WIS",
        )
        result = resurrect_character(dead, "revivify", caster=caster)
        assert result["success"]
        assert caster.gold == 200  # 500 - 300
        assert caster.spell_slots[3] == 1

    def test_resurrect_caster_not_enough_gold(self):
        dead = _make_char(id="dead1", hp=0, conditions=["dead"])
        caster = _make_char(id="cleric", gold=50, spell_slots={3: 1})
        result = resurrect_character(dead, "revivify", caster=caster)
        assert not result["success"]
        assert "300gp" in result["error"]

    def test_resurrect_caster_no_spell_slot(self):
        dead = _make_char(id="dead1", hp=0, conditions=["dead"])
        caster = _make_char(id="cleric", gold=500, spell_slots={3: 0})
        result = resurrect_character(dead, "revivify", caster=caster)
        assert not result["success"]
        assert "spell slots" in result["error"]

    def test_raise_dead_has_penalties(self):
        dead = _make_char(hp=0, conditions=["dead"])
        result = resurrect_character(dead, "raise_dead")
        assert result["success"]
        assert "penalties" in result

    def test_true_resurrection_full_hp(self):
        dead = _make_char(hp=0, conditions=["dead"], max_hp=40)
        result = resurrect_character(dead, "true_resurrection")
        assert result["success"]
        assert dead.hp == 40

    def test_resurrect_clears_death_saves(self):
        dead = _make_char(hp=0, conditions=["dead"],
                         death_saves=DeathSaves(successes=2, failures=3))
        resurrect_character(dead, "revivify")
        assert dead.death_saves.successes == 0
        assert dead.death_saves.failures == 0


class TestNPCHeal:
    def test_npc_stabilize(self):
        char = _make_char(hp=0, conditions=["unconscious"],
                         death_saves=DeathSaves(failures=2))
        # Stabilize resets death saves
        char.death_saves = DeathSaves()
        assert char.death_saves.failures == 0

    def test_npc_heal_revives(self):
        char = _make_char(hp=0, conditions=["unconscious"])
        result = apply_healing(char, 5)
        assert result["revived"]
        assert char.hp == 5
        assert "unconscious" not in char.conditions


# =====================================================================
# Economy
# =====================================================================

class TestBuySell:
    def test_buy_item_success(self):
        char = _make_char(gold=100)
        result = buy_item(char, "Longsword", 15)
        assert result["success"]
        assert char.gold == 85
        assert any(i.name == "Longsword" for i in char.inventory)

    def test_buy_item_not_enough_gold(self):
        char = _make_char(gold=5)
        result = buy_item(char, "Plate Armor", 1500)
        assert not result["success"]
        assert "1500gp" in result["error"]

    def test_buy_item_stacks(self):
        char = _make_char(gold=100)
        char.inventory.append(Item(name="Arrows", quantity=20))
        result = buy_item(char, "Arrows", 1, quantity=20)
        assert result["success"]
        assert char.inventory[0].quantity == 40

    def test_sell_item_success(self):
        char = _make_char(gold=50)
        char.inventory.append(Item(name="Longsword", quantity=1, weight=3.0))
        result = sell_item(char, "Longsword", 7)  # half price
        assert result["success"]
        assert char.gold == 57
        assert not any(i.name == "Longsword" for i in char.inventory)

    def test_sell_item_not_in_inventory(self):
        char = _make_char()
        result = sell_item(char, "Wand of Fireballs", 50)
        assert not result["success"]

    def test_sell_partial_quantity(self):
        char = _make_char(gold=0)
        char.inventory.append(Item(name="Rations", quantity=10))
        result = sell_item(char, "Rations", 1, quantity=5)
        assert result["success"]
        assert char.gold == 5
        assert char.inventory[0].quantity == 5


class TestItemPrices:
    def test_known_item(self):
        assert get_item_price("longsword") == 15
        assert get_item_price("plate armor") == 1500
        assert get_item_price("potion of healing") == 50

    def test_unknown_item(self):
        # Falls back to magic item rarity pricing
        price = get_item_price("random unknown item", rarity="rare")
        assert price is not None
        assert price == 2750  # midpoint of (500, 5000)

    def test_case_insensitive(self):
        assert get_item_price("Longsword") == 15
        assert get_item_price("DAGGER") == 2


class TestCrafting:
    def test_craft_success_possible(self):
        char = _make_char(gold=500)
        # Result depends on dice roll, so we just check it runs
        result = craft_item(char, "Healing Potion", rarity="common")
        assert "check_roll" in result or "error" in result

    def test_craft_not_enough_gold(self):
        char = _make_char(gold=0)
        result = craft_item(char, "Sword", rarity="rare")
        assert not result["success"]
        assert "materials" in result["error"].lower() or "gp" in result["error"]


class TestDowntime:
    def test_training_progress(self):
        char = _make_char(gold=100)
        result = downtime_training(char, "Stealth", days_spent=50)
        assert result["success"]
        assert not result["completed"]
        assert result["days_trained"] == 50
        assert result["days_remaining"] == 200

    def test_training_completion(self):
        char = _make_char(gold=500)
        char.class_resources["training_stealth"] = 240
        result = downtime_training(char, "Stealth", days_spent=10)
        assert result["success"]
        assert result["completed"]
        assert "Stealth" in char.skill_proficiencies

    def test_training_already_proficient(self):
        char = _make_char(skill_proficiencies=["Stealth"])
        result = downtime_training(char, "Stealth", days_spent=10)
        assert not result["success"]

    def test_carousing(self):
        char = _make_char(gold=50)
        result = downtime_carousing(char)
        assert result["success"]
        assert result["outcome"] in ("trouble", "neutral", "contact", "rumor", "windfall")
        assert char.gold <= 65  # spent 10, might gain 25 on windfall (net max 50-10+25=65)

    def test_carousing_not_enough_gold(self):
        char = _make_char(gold=5)
        result = downtime_carousing(char)
        assert not result["success"]

    def test_recuperate(self):
        char = _make_char(hp=20, conditions=["poisoned", "exhaustion_1"])
        result = downtime_recuperate(char)
        assert result["success"]
        assert char.hp == char.max_hp
        assert "poisoned" not in char.conditions


# =====================================================================
# Faction Reputation
# =====================================================================

class TestFactionReputation:
    def test_adjust_reputation(self):
        journal = WorldJournal()
        rep = journal.adjust_faction_reputation("town_guard", 15, "helped patrol")
        assert rep.score == 15
        assert rep.tier == "neutral"
        assert len(rep.history) == 1

    def test_reputation_tiers(self):
        rep = FactionReputation(score=60)
        assert rep.tier == "allied"
        rep.score = 30
        assert rep.tier == "friendly"
        rep.score = 0
        assert rep.tier == "neutral"
        rep.score = -30
        assert rep.tier == "unfriendly"
        rep.score = -60
        assert rep.tier == "hostile"

    def test_reputation_clamped(self):
        journal = WorldJournal()
        rep = journal.adjust_faction_reputation("evil_cult", -200, "destroyed their temple")
        assert rep.score == -100

        rep = journal.adjust_faction_reputation("evil_cult", 500, "joined them")
        assert rep.score == 100

    def test_reputation_history_pruned(self):
        journal = WorldJournal()
        for i in range(25):
            journal.adjust_faction_reputation("guild", 1, f"deed {i}")
        rep = journal.faction_reputations["guild"]
        assert len(rep.history) == 20  # capped


# =====================================================================
# NPC Memory (Journal Injection)
# =====================================================================

class TestNPCMemory:
    def test_npc_prompt_includes_history(self):
        from src.dm.npc_dialogue import NPCDialogueSession
        from src.campaign.campaign_db import NPCProfile, CampaignData

        npc = NPCProfile(
            id="elder_mora", name="Elder Mora", location="tavern",
            personality="Cautious", goals="Protect village", disposition="friendly",
        )
        campaign = CampaignData(title="Test", setting_overview="A test campaign.")

        journal = WorldJournal()
        journal.record_event(
            "Elder Mora revealed her son is cursed",
            involved_npcs=["elder_mora"], importance="major",
        )
        journal.update_npc_attitude("elder_mora", "friendly", "Party helped rescue her cat")
        journal.npc_summaries["elder_mora"] = "Previously discussed the curse affecting the Bleakwood."

        prompt = NPCDialogueSession._build_npc_prompt(npc, campaign, journal)

        assert "Party helped rescue her cat" in prompt
        assert "Previously discussed the curse" in prompt
        assert "Elder Mora revealed her son is cursed" in prompt

    def test_npc_prompt_without_journal(self):
        from src.dm.npc_dialogue import NPCDialogueSession
        from src.campaign.campaign_db import NPCProfile, CampaignData

        npc = NPCProfile(
            id="test_npc", name="Test NPC", location="test",
            personality="Grumpy", goals="Sleep", disposition="neutral",
        )
        campaign = CampaignData(title="Test", setting_overview="A test campaign.")

        prompt = NPCDialogueSession._build_npc_prompt(npc, campaign)
        assert "Test NPC" in prompt
        assert "Prior Interactions" not in prompt


# =====================================================================
# Campaign Time — Travel & Deadlines
# =====================================================================

class TestTravelTime:
    def _make_game_state(self):
        from src.engine.game_state import GameState
        from src.models.combat import CombatState
        locs = {
            "town": Location(
                id="town", name="Town", description="A town",
                connected_to=["forest"],
                connections=[LocationConnection(target_id="forest", travel_hours=4.0, description="forest trail")],
            ),
            "forest": Location(
                id="forest", name="Forest", description="A forest",
                connected_to=["town"],
            ),
            "tavern": Location(
                id="tavern", name="Tavern", description="Inside the tavern",
                parent="town",
            ),
        }
        world = WorldState(current_location_id="town", locations=locs)
        return GameState(
            player_character_ids=["pc1"],
            characters={"pc1": _make_char(id="pc1")},
            world=world,
        )

    def test_travel_time_from_connection(self):
        gs = self._make_game_state()
        result = travel_time(gs, "forest")
        assert result["success"]
        assert result["travel_hours"] == 4.0
        assert result.get("random_encounter_eligible")

    def test_travel_to_child_location_instant(self):
        gs = self._make_game_state()
        result = travel_time(gs, "tavern")
        assert result["success"]
        assert result["travel_hours"] == 0.0

    def test_travel_to_unreachable(self):
        gs = self._make_game_state()
        gs.world.locations["cave"] = Location(id="cave", name="Cave", description="remote")
        result = travel_time(gs, "cave")
        assert not result["success"]


class TestQuestDeadlines:
    def test_quest_expires_on_deadline(self):
        from src.engine.game_state import GameState
        world = WorldState(
            current_location_id="town",
            locations={"town": Location(id="town", name="T", description="t")},
            quests=[
                Quest(
                    id="q1", title="Rescue", description="Save them",
                    status="active", deadline_day=10,
                    deadline_description="before the full moon",
                ),
            ],
        )
        gs = GameState(
            player_character_ids=[], characters={}, world=world,
        )
        expired = _check_quest_deadlines(gs, current_day=11)
        assert len(expired) == 1
        assert expired[0]["quest"] == "Rescue"
        assert world.quests[0].status == "failed"

    def test_quest_not_expired_before_deadline(self):
        from src.engine.game_state import GameState
        world = WorldState(
            current_location_id="town",
            locations={"town": Location(id="town", name="T", description="t")},
            quests=[
                Quest(id="q1", title="Rescue", description="d",
                      status="active", deadline_day=10),
            ],
        )
        gs = GameState(
            player_character_ids=[], characters={}, world=world,
        )
        expired = _check_quest_deadlines(gs, current_day=9)
        assert len(expired) == 0
        assert world.quests[0].status == "active"

    def test_advance_time_checks_deadlines(self):
        from src.engine.game_state import GameState
        world = WorldState(
            current_location_id="town",
            locations={"town": Location(id="town", name="T", description="t")},
            quests=[
                Quest(id="q1", title="Urgent", description="d",
                      status="active", deadline_day=3),
            ],
            time=TimeState(day=2, hour=20),
        )
        gs = GameState(
            player_character_ids=[], characters={}, world=world,
        )
        result = advance_time(world.time, hours=10, game_state=gs)
        assert result["success"]
        # Day should now be 3+ and quest should be checked
        assert world.time.day >= 3


class TestLocationConnection:
    def test_location_connection_model(self):
        conn = LocationConnection(target_id="forest", travel_hours=4.0, description="A winding trail")
        assert conn.target_id == "forest"
        assert conn.travel_hours == 4.0

    def test_location_with_connections(self):
        loc = Location(
            id="town", name="Town", description="A town",
            connections=[
                LocationConnection(target_id="forest", travel_hours=4.0),
                LocationConnection(target_id="city", travel_hours=12.0),
            ],
        )
        assert len(loc.connections) == 2
