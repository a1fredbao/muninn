"""Tests for session orchestration and async plugin hooks."""

import asyncio
import time
from pathlib import Path

from muninn.core.state import StateManager
from muninn.plugin_api import BaseTrainingPlugin
from muninn.services.manifest import PackManifest
from muninn.services.plugin_loader import (
    InProcessPluginAdapter,
    LoadedPlugin,
)
from muninn.services.training_session import TrainingSession


class _Plugin(BaseTrainingPlugin):
    def __init__(self, matcher, problem_ids=None):
        self.matcher = matcher
        self.ids = problem_ids or ["1"]
        super().__init__("")

    def load_data(self):
        return None

    def get_all_problem_ids(self):
        return self.ids

    def render_statement(self, problem_id):
        return f"Question {problem_id}"

    def check_answer(self, problem_id, user_input):
        return self.matcher(problem_id, user_input)

    def get_expected_display(self, problem_id):
        return "1"


def _adapter(plugin: BaseTrainingPlugin, pack_id: str = "test"):
    fake_dir = Path("/tmp") / pack_id
    loaded = LoadedPlugin(
        pack_id=pack_id,
        pack_dir=fake_dir,
        manifest=PackManifest(
            id=pack_id,
            name=pack_id,
            version="1.0.0",
            entrypoint="plugin:Plugin",
            api_version="1",
        ),
        entrypoint="plugin:Plugin",
        environment={},
    )
    return InProcessPluginAdapter(loaded, plugin)


async def _session(plugin: BaseTrainingPlugin, tmp_path, pack_id="test"):
    store = StateManager(pack_id, str(tmp_path / "states"))
    return await TrainingSession.create(
        pack_id,
        _adapter(plugin, pack_id),
        store,
    )


def test_sync_plugin_judging_keeps_event_loop_responsive(tmp_path):
    def slow_match(problem_id, user_input):
        time.sleep(0.25)
        return user_input == problem_id

    session = asyncio.run(_session(_Plugin(slow_match), tmp_path, "slow"))

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


def test_async_plugin_is_awaited(tmp_path):
    async def async_match(problem_id, user_input):
        await asyncio.sleep(0)
        return user_input == problem_id

    plugin = _Plugin(lambda problem_id, user_input: False)
    plugin.check_answer = async_match
    session = asyncio.run(_session(plugin, tmp_path, "async"))

    assert asyncio.run(session.submit_answer("1", "1", 0.1))
    session.close()


def test_session_accumulates_stats_after_judging(tmp_path):
    session = asyncio.run(
        _session(
            _Plugin(lambda problem_id, user_input: user_input == problem_id),
            tmp_path,
            "stats",
        )
    )

    assert asyncio.run(session.submit_answer("1", "1", 1.5))
    stats = session.stats()

    assert stats.total_count == 1
    assert stats.ac_count == 1
    assert stats.distinct_ac == 1
    assert stats.combo == 1
    assert stats.avg_time == 1.5
    session.close()


def test_skip_problem_removes_it_once_and_updates_total(tmp_path):
    plugin = _Plugin(lambda problem_id, user_input: True, ["1", "2"])
    session = asyncio.run(_session(plugin, tmp_path, "skip"))
    problem_id = session.next_problem()
    assert problem_id is not None

    session.skip_problem(problem_id)
    session.skip_problem(problem_id)

    remaining = set()
    while (next_problem := session.next_problem()) is not None:
        remaining.add(next_problem)

    assert problem_id not in remaining
    assert session.stats().total_problems == 1
    session.close()


def test_session_migrates_legacy_problem_progress(tmp_path):
    class MigratingPlugin(_Plugin):
        def get_legacy_problem_id_map(self):
            return {"0__typeA": "q1::typeA"}

    store = StateManager("migrate", str(tmp_path / "states"))
    store.update_stats("0__typeA", is_ac=True, time_spent=2.0)
    plugin = MigratingPlugin(
        lambda problem_id, user_input: True,
        ["q1::typeA"],
    )
    session = asyncio.run(
        TrainingSession.create(
            "migrate",
            _adapter(plugin, "migrate"),
            store,
        )
    )

    stats = session.stats()
    assert stats.total_count == 1
    assert stats.ac_count == 1
    assert stats.avg_time == 2.0
    session.close()
