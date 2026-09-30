"""Tests for multi-question-type training sessions."""

import asyncio
import time
from pathlib import Path

from muninn.plugin_api import BaseTrainingPlugin
from muninn.services.manifest import PackManifest
from muninn.services.plugin_loader import (
    InProcessPluginAdapter,
    LoadedPlugin,
)
from muninn.services.training_session import QuestionRoute, TrainingSession


class _QuestionType:
    key = "questions"
    label = "Questions"
    description = "Test question type"

    def __init__(self, matcher, problem_ids=None):
        self.matcher = matcher
        self.ids = problem_ids or ["1"]

    def get_all_problem_ids(self):
        return self.ids

    def describe_problem(self, problem_id):
        del problem_id

    def render_statement(self, problem_id):
        return f"Question {problem_id}"

    def check_answer(self, problem_id, user_input):
        return self.matcher(problem_id, user_input)

    def get_expected_display(self, problem_id):
        return "1"

    def get_expand_info(self, problem_id):
        del problem_id
        return ""


class _Plugin(BaseTrainingPlugin):
    def __init__(self, matcher, problem_ids=None):
        self.question_type = _QuestionType(matcher, problem_ids)
        super().__init__("")

    def get_question_types(self):
        return [self.question_type]


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
            api_version="2",
        ),
        entrypoint="plugin:Plugin",
        environment={},
    )
    return InProcessPluginAdapter(loaded, plugin)


async def _session(plugin: BaseTrainingPlugin, tmp_path, pack_id="test"):
    adapter = _adapter(plugin, pack_id)
    return await TrainingSession.create(
        [
            QuestionRoute(
                pack_id=pack_id,
                question_type_id=plugin.question_type.key,
                plugin=adapter,
            )
        ],
        state_dir=str(tmp_path / "states"),
    )


def test_sync_plugin_judging_keeps_event_loop_responsive(tmp_path):
    def slow_match(problem_id, user_input):
        time.sleep(0.25)
        return user_input == problem_id

    session = asyncio.run(_session(_Plugin(slow_match), tmp_path, "slow"))

    async def exercise():
        ticks = 0
        problem_id = session.next_problem()
        assert problem_id is not None
        task = asyncio.create_task(session.submit_answer(problem_id, "1", 0.25))
        while not task.done():
            await asyncio.sleep(0.01)
            ticks += 1
        assert await task
        return ticks

    assert asyncio.run(exercise()) >= 5
    session.close()


def test_async_plugin_is_awaited(tmp_path):
    async def async_match(problem_id, user_input):
        await asyncio.sleep(0)
        return user_input == problem_id

    plugin = _Plugin(lambda problem_id, user_input: False)
    plugin.question_type.matcher = async_match
    session = asyncio.run(_session(plugin, tmp_path, "async"))
    problem_id = session.next_problem()
    assert problem_id is not None

    assert asyncio.run(session.submit_answer(problem_id, "1", 0.1))
    session.close()


def test_session_accumulates_stats_after_judging(tmp_path):
    session = asyncio.run(
        _session(
            _Plugin(lambda problem_id, user_input: user_input == problem_id),
            tmp_path,
            "stats",
        )
    )
    problem_id = session.next_problem()
    assert problem_id is not None
    assert asyncio.run(session.submit_answer(problem_id, "1", 1.5))

    stats = session.stats()
    assert stats.total_count == 1
    assert stats.ac_count == 1
    assert stats.distinct_ac == 1
    assert stats.combo == 1
    assert stats.avg_time == 1.5
    session.close()


def test_skip_problem_removes_it_from_session(tmp_path):
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
