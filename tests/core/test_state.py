"""Tests for src/core/state.py."""

import os
import shutil
import tempfile

import pytest

from src.core.state import StateManager


class TestStateManager:
    @pytest.fixture
    def state_manager(self, monkeypatch):
        """Return a StateManager whose DB lives in an ephemeral directory,
        isolated from the real ``~/.muninn`` on all platforms."""
        tmp = tempfile.mkdtemp()

        original_expanduser = os.path.expanduser

        def _expanduser(path):
            # Match both Unix "~/" and Windows "~\\" (via os.sep).
            if path.startswith(("~" + os.sep, "~/")):
                return os.path.join(tmp, path[2:])
            if path == "~":
                return tmp
            return original_expanduser(path)

        monkeypatch.setattr(os.path, "expanduser", _expanduser)

        sm = StateManager("test_pack")
        yield sm
        sm.close()
        shutil.rmtree(tmp, ignore_errors=True)

    def test_init_creates_db_file(self, state_manager):
        assert os.path.isfile(state_manager.db_path)

    def test_default_stats_for_unknown_problem(self, state_manager):
        stats = state_manager.get_stats("nonexistent")
        assert stats == {"ac_count": 0, "total_count": 0, "total_ac_time": 0.0}

    def test_update_stats_and_retrieve(self, state_manager):
        state_manager.update_stats("p1", is_ac=True, time_spent=2.5)
        stats = state_manager.get_stats("p1")
        assert stats["ac_count"] == 1
        assert stats["total_count"] == 1
        assert stats["total_ac_time"] == 2.5

    def test_incorrect_answer_does_not_increment_ac(self, state_manager):
        state_manager.update_stats("p1", is_ac=False, time_spent=3.0)
        stats = state_manager.get_stats("p1")
        assert stats["ac_count"] == 0
        assert stats["total_count"] == 1
        assert stats["total_ac_time"] == 0.0

    def test_multiple_updates_accumulate(self, state_manager):
        state_manager.update_stats("p1", is_ac=True, time_spent=1.0)
        state_manager.update_stats("p1", is_ac=False, time_spent=2.0)
        state_manager.update_stats("p1", is_ac=True, time_spent=3.0)
        stats = state_manager.get_stats("p1")
        assert stats["ac_count"] == 2
        assert stats["total_count"] == 3
        assert stats["total_ac_time"] == 4.0

    def test_independent_problem_ids(self, state_manager):
        state_manager.update_stats("a", is_ac=True, time_spent=1.0)
        state_manager.update_stats("b", is_ac=False, time_spent=2.0)
        a = state_manager.get_stats("a")
        b = state_manager.get_stats("b")
        assert a["total_count"] == 1
        assert b["total_count"] == 1
        assert a["ac_count"] == 1
        assert b["ac_count"] == 0
