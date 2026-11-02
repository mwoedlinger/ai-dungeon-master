"""The CLI combat loop's routing of turn-driver outcomes.

`SessionManager` had no test coverage, and its combat loop was just rewritten
to delegate to the shared driver. These tests pin the routing — which outcome
leads to which UI action — without touching the LLM or the terminal.
"""
from __future__ import annotations

import pytest

from src.engine.turn_driver import (
    AutoSkipped,
    AwaitPlayerInput,
    CombatEnded,
    DeathSaveResolved,
    MonsterTurn,
    TurnLimitReached,
)
from src.interface.session import SessionManager, TurnMode


class FakeDriver:
    """Returns scripted outcomes and records forced turn-ends."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.finished: list[str] = []

    def next_turn(self):
        return self.outcomes.pop(0)

    def finish_monster_turn(self, cid):
        self.finished.append(cid)
        return True

    def finish_player_turn(self, cid):
        self.finished.append(cid)
        return False


@pytest.fixture
def session(game_state_with_goblins, campaign_stub, event_log, tmp_path, monkeypatch):
    from src.dm.dungeon_master import DungeonMaster
    from tests.support.scripted_backend import ScriptedBackend

    dm = DungeonMaster(
        game_state_with_goblins, campaign_stub, event_log,
        save_path=str(tmp_path / "s.json"),
        backend=ScriptedBackend.narration("..."),
    )
    sm = SessionManager(dm, game_state_with_goblins, event_log,
                        save_path=str(tmp_path / "s.json"))
    sm.mode = TurnMode.COMBAT
    # Keep the LLM and the terminal out of it.
    sm.rendered = []
    monkeypatch.setattr(
        sm, "_process_and_render",
        lambda text, **kw: sm.rendered.append((text, kw)),
    )
    return sm


def _drive(session, outcome):
    session._turn_driver = FakeDriver([outcome])
    session._combat_input_loop()
    return session._turn_driver


class TestOutcomeRouting:
    def test_combat_ended_returns_to_exploration(self, session):
        _drive(session, CombatEnded())
        assert session.mode is TurnMode.EXPLORATION

    def test_auto_skip_renders_nothing(self, session):
        _drive(session, AutoSkipped("goblin_1", "Goblin", "defeated"))
        assert session.rendered == []
        assert session.mode is TurnMode.COMBAT

    def test_monster_turn_is_rendered_through_the_dm(self, session):
        driver = _drive(session, MonsterTurn("goblin_1", "Goblin", "[DM: go]"))
        assert session.rendered == [("[DM: go]", {"combat": True, "turn_scope": "goblin_1"})]
        # The stuck-turn guard must always run after a monster render.
        assert driver.finished == ["goblin_1"]

    def test_death_save_is_rendered_and_not_sent_to_the_llm(self, session):
        _drive(session, DeathSaveResolved(
            "aldric", "Aldric", {"roll": 12}, "rolled", "Aldric rolls a death save: 12",
        ))
        assert session.rendered == []  # resolved by the engine, not the DM

    def test_turn_limit_ends_combat(self, session, game_state_with_goblins):
        from src.engine.combat import start_combat
        start_combat(game_state_with_goblins, ["aldric", "goblin_1"])
        _drive(session, TurnLimitReached(turns=50))
        assert session.mode is TurnMode.EXPLORATION
        assert game_state_with_goblins.combat.active is False

    def test_player_turn_prompts_and_renders(self, session, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "I attack the goblin")
        monkeypatch.setattr(session, "_show_combat_status", lambda: None)
        _drive(session, AwaitPlayerInput("aldric", "Aldric"))
        text, kwargs = session.rendered[0]
        assert text == "[Aldric]: I attack the goblin"
        assert kwargs["turn_scope"] == "aldric"

    def test_empty_input_does_not_call_the_dm(self, session, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "   ")
        monkeypatch.setattr(session, "_show_combat_status", lambda: None)
        _drive(session, AwaitPlayerInput("aldric", "Aldric"))
        assert session.rendered == []

    def test_slash_command_does_not_call_the_dm(self, session, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "/help")
        monkeypatch.setattr(session, "_show_combat_status", lambda: None)
        _drive(session, AwaitPlayerInput("aldric", "Aldric"))
        assert session.rendered == []

    def test_quit_raises_eof(self, session, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "quit")
        monkeypatch.setattr(session, "_show_combat_status", lambda: None)
        with pytest.raises(EOFError):
            _drive(session, AwaitPlayerInput("aldric", "Aldric"))


class TestDeathSaveStyling:
    @pytest.mark.parametrize(
        "kind", ["died", "recovered", "stabilized", "stable_skip", "failed", "rolled"],
    )
    def test_every_kind_has_a_style(self, kind):
        assert kind in SessionManager._DEATH_SAVE_STYLES

    def test_unknown_kind_falls_back(self, session):
        session._render_death_save(
            DeathSaveResolved("aldric", "Aldric", {}, "surprise", "something new"),
        )  # must not raise
