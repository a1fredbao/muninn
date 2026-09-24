"""Tests for session orchestration and sync/async judging."""

import asyncio
import time
from unittest.mock import MagicMock

from src.core.base_plugin import BaseRecitePlugin
from src.services.study_session import StudySession


class _Plugin(BaseRecitePlugin):
    def __init__(self, matcher):
        self.matcher = matcher
        super().__init__("")

    def load_data(self):
        self.ids = ["1"]

    def get_all_problem_ids(self):
        return self.ids

    def render_statement(self, problem_id):
        return f"Question {problem_id}"

    def check_answer(self, problem_id, user_input):
        return self.matcher(problem_id, user_input)

    def get_expected_display(self, problem_id):
        return "1"


def _state_manager() -> MagicMock:
    state = MagicMock()
    stats = {"ac_count": 0, "total_count": 0, "total_ac_time": 0.0}
    state.get_stats.return_value = stats
    return state


def test_sync_plugin_judging_keeps_event_loop_responsive():
    def slow_match(problem_id, user_input):
        time.sleep(0.25)
        return user_input == problem_id

    session = StudySession("slow", _Plugin(slow_match), _state_manager())

    async def exercise():
        ticks = 0
        task = asyncio.create_task(session.submit_answer("1", "1", 0.25))
        while not task.done():
            await asyncio.sleep(0.01)
            ticks += 1
        assert await task
        return ticks

    ticks = asyncio.run(exercise())
    assert ticks >= 5
    session.close()


def test_async_plugin_is_awaited():
    async def async_match(problem_id, user_input):
        await asyncio.sleep(0)
        return user_input == problem_id

    plugin = _Plugin(lambda problem_id, user_input: False)
    plugin.check_answer = async_match
    session = StudySession("async", plugin, _state_manager())

    assert asyncio.run(session.submit_answer("1", "1", 0.1))
    assert session.async_judge
    session.close()


def test_session_accumulates_stats_after_judging():
    state = _state_manager()
    state.get_stats.side_effect = lambda problem_id: {
        "ac_count": 0,
        "total_count": 0,
        "total_ac_time": 0.0,
    }
    session = StudySession(
        "stats",
        _Plugin(lambda problem_id, user_input: user_input == problem_id),
        state,
    )

    assert asyncio.run(session.submit_answer("1", "1", 1.5))
    stats = session.stats()

    assert stats.total_count == 1
    assert stats.ac_count == 1
    assert stats.distinct_ac == 1
    assert stats.combo == 1
    assert stats.avg_time == 1.5
    session.close()


def test_skip_problem_removes_it_once_and_updates_total():
    plugin = _Plugin(lambda problem_id, user_input: True)
    plugin.ids = ["1", "2"]
    state = _state_manager()
    session = StudySession("skip", plugin, state)
    problem_id = session.next_problem()
    assert problem_id is not None

    session.skip_problem(problem_id)
    session.skip_problem(problem_id)

    remaining = set()
    while (next_problem := session.next_problem()) is not None:
        remaining.add(next_problem)

    assert problem_id not in remaining
    assert session.stats().total_problems == 1
    state.update_stats.assert_not_called()
    session.close()
