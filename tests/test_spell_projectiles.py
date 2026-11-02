"""A3: multi-projectile spells roll each projectile separately.

Magic Missile fires three darts, Scorching Ray three rays, Eldritch Blast up
to four beams. Rolling once for the spell (or once per target) understates
their damage by 3x and, for Magic Missile, meant the engine did not resolve
the spell at all — its description instructed the LLM to do the arithmetic.
"""
from __future__ import annotations

import pytest

from src.data.srd_client import get_spell
from src.engine.spells import _distribute, projectile_count, resolve_spell


class TestProjectileCount:
    def test_magic_missile_fires_three(self, wizard):
        spell = get_spell("Magic Missile")
        assert projectile_count(spell, wizard, cast_level=1) == 3

    def test_magic_missile_upcast_adds_darts(self, wizard):
        spell = get_spell("Magic Missile")
        assert projectile_count(spell, wizard, cast_level=3) == 5

    def test_scorching_ray_fires_three(self, wizard):
        spell = get_spell("Scorching Ray")
        assert projectile_count(spell, wizard, cast_level=2) == 3

    @pytest.mark.parametrize("level,beams", [(1, 1), (4, 1), (5, 2), (10, 2), (11, 3), (17, 4)])
    def test_eldritch_blast_scales_with_character_level(self, wizard, level, beams):
        wizard.level = level
        assert projectile_count(get_spell("Eldritch Blast"), wizard, cast_level=0) == beams

    def test_ordinary_spell_fires_one(self, wizard):
        assert projectile_count(get_spell("Fire Bolt"), wizard, cast_level=0) == 1


class TestDistribution:
    def test_all_projectiles_hit_a_lone_target(self):
        assert _distribute(3, ["a"]) == ["a", "a", "a"]

    def test_round_robin_across_targets(self):
        assert _distribute(3, ["a", "b"]) == ["a", "b", "a"]

    def test_no_targets_is_safe(self):
        assert _distribute(3, []) == []


class TestSpellData:
    def test_magic_missile_is_engine_resolved(self):
        """It used to be `narrative`, which left the maths to the LLM."""
        spell = get_spell("Magic Missile")
        assert str(spell.resolution) == "SpellResolution.AUTO_DAMAGE"
        assert spell.damage_dice == "1d4+1"

    def test_description_no_longer_instructs_the_llm_to_roll(self):
        desc = get_spell("Magic Missile").description.lower()
        assert "roll_dice" not in desc
        assert "three separate times" not in desc

    def test_projectile_upcast_does_not_also_scale_damage(self):
        """Otherwise a 3rd-level Magic Missile gets both extra darts and dice."""
        for name in ("Magic Missile", "Scorching Ray"):
            assert get_spell(name).upcast_pattern == "targets"


class TestResolution:
    def test_magic_missile_deals_three_darts_to_one_target(
        self, game_state_with_goblins, wizard,
    ):
        gs = game_state_with_goblins
        goblin = gs.characters["goblin_1"]
        goblin.hp = goblin.max_hp = 60
        result = resolve_spell(
            gs, get_spell("Magic Missile"), wizard, [goblin], cast_level=1,
        )
        assert result["projectiles"] == 3
        assert len(result["projectile_hits"]) == 3
        # 3 x (1d4+1) => 6..15, never a single dart's 2..5
        assert 6 <= result["total_damage"] <= 15
        assert result["targets"][0]["projectiles"] == 3

    def test_magic_missile_splits_across_targets(self, game_state_with_goblins, wizard):
        gs = game_state_with_goblins
        for cid in ("goblin_1", "goblin_2"):
            gs.characters[cid].hp = gs.characters[cid].max_hp = 60
        targets = [gs.characters["goblin_1"], gs.characters["goblin_2"]]
        result = resolve_spell(gs, get_spell("Magic Missile"), wizard, targets, cast_level=1)

        by_name = {t["target"]: t for t in result["targets"]}
        assert sorted(t["projectiles"] for t in by_name.values()) == [1, 2]
        assert sum(t["projectiles"] for t in by_name.values()) == 3

    def test_upcast_magic_missile_fires_five(self, game_state_with_goblins, wizard):
        gs = game_state_with_goblins
        goblin = gs.characters["goblin_1"]
        goblin.hp = goblin.max_hp = 90
        wizard.spell_slots[3] = 1
        wizard.max_spell_slots[3] = 1
        result = resolve_spell(
            gs, get_spell("Magic Missile"), wizard, [goblin], cast_level=3,
        )
        assert result["projectiles"] == 5
        assert 10 <= result["total_damage"] <= 25

    def test_scorching_ray_rolls_three_attacks(self, game_state_with_goblins, wizard):
        gs = game_state_with_goblins
        goblin = gs.characters["goblin_1"]
        goblin.hp = goblin.max_hp = 90
        result = resolve_spell(
            gs, get_spell("Scorching Ray"), wizard, [goblin], cast_level=2,
        )
        assert result["projectiles"] == 3
        assert len(result["targets"]) == 3  # one entry per independent attack
        # Rays hit or miss independently — not all-or-nothing.
        assert all("hits" in r for r in result["targets"])

    def test_single_projectile_spell_reports_no_projectile_keys(
        self, game_state_with_goblins, wizard,
    ):
        gs = game_state_with_goblins
        result = resolve_spell(
            gs, get_spell("Fire Bolt"), wizard, [gs.characters["goblin_1"]], cast_level=0,
        )
        assert "projectiles" not in result

    def test_damage_actually_lands_on_the_target(self, game_state_with_goblins, wizard):
        gs = game_state_with_goblins
        goblin = gs.characters["goblin_1"]
        goblin.hp = goblin.max_hp = 60
        before = goblin.hp
        result = resolve_spell(
            gs, get_spell("Magic Missile"), wizard, [goblin], cast_level=1,
        )
        assert before - goblin.hp == result["total_damage"]
