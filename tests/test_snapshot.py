"""Turn snapshots and /retcon.

Undo has one hard constraint and one subtle one: the campaign's lazily-loaded
entity cache must never be deep-copied, and restore must mutate the existing
GameState in place because six objects hold direct references to it.
"""
from __future__ import annotations

import pytest

from src.engine.snapshot import SnapshotStack, restore_state, snapshot_state


class Undeepcopyable:
    """Stands in for CampaignData's LRU cache of disk-loaded entities."""

    def __deepcopy__(self, memo):
        raise AssertionError("campaign must never be deep-copied")


class TestCampaignIsAliased:
    def test_campaign_is_not_deep_copied(self, game_state):
        game_state.campaign = Undeepcopyable()
        snapshot_state(game_state)  # must not raise

    def test_campaign_is_shared_with_the_snapshot(self, game_state):
        game_state.campaign = Undeepcopyable()
        snap = snapshot_state(game_state)
        assert snap.campaign is game_state.campaign

    def test_original_keeps_its_campaign(self, game_state):
        campaign = Undeepcopyable()
        game_state.campaign = campaign
        snapshot_state(game_state)
        assert game_state.campaign is campaign

    def test_campaign_survives_a_failed_copy(self, game_state, monkeypatch):
        campaign = Undeepcopyable()
        game_state.campaign = campaign
        import src.engine.snapshot as snap_mod
        monkeypatch.setattr(snap_mod.copy, "deepcopy",
                            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            snapshot_state(game_state)
        assert game_state.campaign is campaign  # the finally block restored it

    def test_restore_leaves_campaign_alone(self, game_state):
        game_state.campaign = Undeepcopyable()
        snap = snapshot_state(game_state)
        campaign = game_state.campaign
        restore_state(game_state, snap)
        assert game_state.campaign is campaign


class TestIndependence:
    def test_snapshot_does_not_track_later_mutations(self, game_state):
        snap = snapshot_state(game_state)
        game_state.characters["aldric"].hp = 3
        assert snap.characters["aldric"].hp == 28

    def test_restore_rewinds_hp(self, game_state):
        snap = snapshot_state(game_state)
        game_state.characters["aldric"].hp = 3
        restore_state(game_state, snap)
        assert game_state.characters["aldric"].hp == 28

    def test_restore_rewinds_conversation_history(self, game_state):
        snap = snapshot_state(game_state)
        game_state.conversation_history.append({"role": "user", "content": "oops"})
        restore_state(game_state, snap)
        assert game_state.conversation_history == []

    def test_restore_mutates_in_place(self, game_state):
        """Six objects hold this reference; rebinding would strand them."""
        alias = game_state
        original_id = id(game_state)
        snap = snapshot_state(game_state)
        game_state.characters["aldric"].hp = 3
        restore_state(game_state, snap)
        assert id(game_state) == original_id
        assert alias.characters["aldric"].hp == 28

    def test_the_same_snapshot_restores_twice(self, game_state):
        snap = snapshot_state(game_state)
        for _ in range(2):
            game_state.characters["aldric"].hp = 3
            restore_state(game_state, snap)
            assert game_state.characters["aldric"].hp == 28

    def test_restore_rewinds_combat_and_journal(self, game_state):
        snap = snapshot_state(game_state)
        game_state.combat.active = True
        game_state.journal.set_flag("bridge_destroyed")
        restore_state(game_state, snap)
        assert game_state.combat.active is False
        assert game_state.journal.get_flag("bridge_destroyed") is None


class TestSnapshotStack:
    def test_bounded_depth(self, game_state):
        stack = SnapshotStack(game_state, max_depth=5)
        for i in range(8):
            game_state.characters["aldric"].hp = 28 - i
            stack.push(f"turn {i}")
        assert len(stack) == 5

    def test_restores_the_most_recent_turn(self, game_state):
        stack = SnapshotStack(game_state)
        stack.push("first")
        game_state.characters["aldric"].hp = 20
        stack.push("second")
        game_state.characters["aldric"].hp = 10

        assert stack.pop_and_restore() == "second"
        assert game_state.characters["aldric"].hp == 20

    def test_unwinds_turn_by_turn(self, game_state):
        stack = SnapshotStack(game_state)
        for hp in (28, 20, 12):
            stack.push(f"hp {hp}")
            game_state.characters["aldric"].hp = hp - 8
        stack.pop_and_restore()
        assert game_state.characters["aldric"].hp == 12
        stack.pop_and_restore()
        assert game_state.characters["aldric"].hp == 20

    def test_empty_stack_returns_none(self, game_state):
        assert SnapshotStack(game_state).pop_and_restore() is None

    def test_oldest_snapshots_are_dropped_not_the_newest(self, game_state):
        stack = SnapshotStack(game_state, max_depth=2)
        game_state.characters["aldric"].hp = 28
        stack.push("a")
        game_state.characters["aldric"].hp = 20
        stack.push("b")
        game_state.characters["aldric"].hp = 12
        stack.push("c")
        assert stack.pop_and_restore() == "c"
        assert game_state.characters["aldric"].hp == 12


class TestRetconCommand:
    def _ctx(self, dm, game_state, tmp_path):
        from src.interface.commands import CommandContext
        return CommandContext(game_state=game_state, dm=dm, save_path=str(tmp_path / "s.json"))

    def test_reports_when_there_is_nothing_to_undo(self, dungeon_master, game_state, tmp_path):
        from src.interface.commands import try_handle_command
        assert try_handle_command("/retcon", self._ctx(dungeon_master, game_state, tmp_path))

    def test_restores_state(self, dungeon_master, game_state, tmp_path):
        from src.interface.commands import try_handle_command
        dungeon_master.snapshots.push("I attack the king")
        game_state.characters["aldric"].hp = 1
        try_handle_command("/retcon", self._ctx(dungeon_master, game_state, tmp_path))
        assert game_state.characters["aldric"].hp == 28

    def test_undo_is_an_alias(self, dungeon_master, game_state, tmp_path):
        from src.interface.commands import try_handle_command
        dungeon_master.snapshots.push("something")
        game_state.characters["aldric"].hp = 1
        try_handle_command("/undo", self._ctx(dungeon_master, game_state, tmp_path))
        assert game_state.characters["aldric"].hp == 28

    def test_context_manager_is_resynced(self, dungeon_master, game_state, tmp_path):
        from src.interface.commands import try_handle_command
        cm = dungeon_master.context_manager
        dungeon_master.snapshots.push("turn")
        game_state.journal.conversation_summary = "A dragon ate the party."
        cm.story_summary = "A dragon ate the party."
        cm.last_actual_prompt_tokens = 90_000
        try_handle_command("/retcon", self._ctx(dungeon_master, game_state, tmp_path))
        assert cm.story_summary == ""
        assert cm.last_actual_prompt_tokens == 0


class TestEndToEnd:
    def test_a_whole_turn_can_be_undone(self, game_state, campaign_stub, event_log, tmp_path):
        from src.dm.dungeon_master import DungeonMaster
        from tests.support.scripted_backend import ScriptedBackend

        backend = ScriptedBackend.tools_then_narration(
            [("apply_damage", {"target_id": "aldric", "amount": 12, "damage_type": "fire"})],
            "Flames engulf him.",
        )
        dm = DungeonMaster(game_state, campaign_stub, event_log,
                           save_path=str(tmp_path / "s.json"), backend=backend)

        dm.snapshots.push("I walk into the fire")
        dm.process_player_input("I walk into the fire")
        assert game_state.characters["aldric"].hp == 16
        assert len(game_state.conversation_history) > 0

        dm.snapshots.pop_and_restore()
        dm.context_manager.resync_from_state()

        assert game_state.characters["aldric"].hp == 28
        assert game_state.conversation_history == []
