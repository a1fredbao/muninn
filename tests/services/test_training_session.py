"""Tests for multi-question-type training sessions."""

import asyncio
import time
from pathlib import Path

import pytest

from muninn.plugin_api import BaseTrainingPlugin
from muninn.services.manifest import PackManifest
from muninn.services.plugin_loader import (
    InProcessPluginAdapter,
    LoadedPlugin,
)
from muninn.services.training_session import (
    AnswerAcceptanceRequired,
    QuestionRoute,
    TrainingSession,
)


class _QuestionType:
    key = "questions"
    label = "Questions"
    description = "Test question type"

    def __init__(self, matcher, problem_ids=None, allow_user_acceptance=False):
        self.matcher = matcher
        self.ids = problem_ids or ["1"]
        self.allow_user_acceptance = allow_user_acceptance

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
    def __init__(self, matcher, problem_ids=None, allow_user_acceptance=False):
        self.question_type = _QuestionType(
            matcher,
            problem_ids,
            allow_user_acceptance,
        )
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


def test_user_acceptance_is_required_after_strict_mismatch(tmp_path):
    plugin = _Plugin(
        lambda problem_id, user_input: False,
        allow_user_acceptance=True,
    )
    session = asyncio.run(_session(plugin, tmp_path, "acceptance-required"))
    problem_id = session.next_problem()
    assert problem_id is not None

    with pytest.raises(AnswerAcceptanceRequired):
        asyncio.run(session.submit_answer_result(problem_id, "同义答案", 0.5))

    assert session.stats().total_count == 0
    session.close()


def test_strict_match_skips_user_acceptance(tmp_path):
    plugin = _Plugin(
        lambda problem_id, user_input: True,
        allow_user_acceptance=True,
    )
    session = asyncio.run(_session(plugin, tmp_path, "acceptance-strict"))
    problem_id = session.next_problem()
    assert problem_id is not None

    result = asyncio.run(session.submit_answer_result(problem_id, "correct", 0.5))

    assert result.outcome.is_correct
    assert not result.outcome.user_confirmed
    session.close()


def test_accepted_answer_is_persisted_and_reused(tmp_path):
    plugin = _Plugin(
        lambda problem_id, user_input: False,
        allow_user_acceptance=True,
    )
    session = asyncio.run(_session(plugin, tmp_path, "acceptance-accept"))
    problem_id = session.next_problem()
    assert problem_id is not None

    result = session.submit_answer_confirmation(
        problem_id,
        "同义答案",
        0.5,
        True,
    )

    assert result.outcome.is_correct
    assert result.outcome.user_confirmed
    assert session.stats().ac_count == 1
    assert session.stats().total_count == 1
    session.close()

    second_plugin = _Plugin(
        lambda problem_id, user_input: False,
        allow_user_acceptance=True,
    )
    second_session = asyncio.run(_session(second_plugin, tmp_path, "acceptance-accept"))
    second_problem_id = second_session.next_problem()
    assert second_problem_id is not None

    second_result = asyncio.run(
        second_session.submit_answer_result(
            second_problem_id,
            "同义答案",
            0.5,
        )
    )

    assert second_result.outcome.is_correct
    assert second_result.outcome.user_confirmed
    second_session.close()


def test_rejected_answer_is_persisted_and_reused(tmp_path):
    plugin = _Plugin(
        lambda problem_id, user_input: False,
        allow_user_acceptance=True,
    )
    session = asyncio.run(_session(plugin, tmp_path, "acceptance-reject"))
    problem_id = session.next_problem()
    assert problem_id is not None

    result = session.submit_answer_confirmation(
        problem_id,
        "错误答案",
        0.5,
        False,
    )

    assert not result.outcome.is_correct
    assert result.outcome.user_confirmed
    assert session.stats().ac_count == 0
    assert session.stats().total_count == 1
    session.close()

    second_plugin = _Plugin(
        lambda problem_id, user_input: False,
        allow_user_acceptance=True,
    )
    second_session = asyncio.run(_session(second_plugin, tmp_path, "acceptance-reject"))
    second_problem_id = second_session.next_problem()
    assert second_problem_id is not None

    second_result = asyncio.run(
        second_session.submit_answer_result(
            second_problem_id,
            "错误答案",
            0.5,
        )
    )

    assert not second_result.outcome.is_correct
    assert second_result.outcome.user_confirmed
    second_session.close()


def test_plugin_without_user_acceptance_records_wrong(tmp_path):
    plugin = _Plugin(lambda problem_id, user_input: False)
    session = asyncio.run(_session(plugin, tmp_path, "acceptance-disabled"))
    problem_id = session.next_problem()
    assert problem_id is not None

    result = asyncio.run(session.submit_answer_result(problem_id, "错误答案", 0.5))

    assert not result.outcome.is_correct
    assert not result.outcome.user_confirmed
    session.close()


def test_noninteractive_submit_treats_pending_confirmation_as_wrong(tmp_path):
    plugin = _Plugin(
        lambda problem_id, user_input: False,
        allow_user_acceptance=True,
    )
    session = asyncio.run(_session(plugin, tmp_path, "acceptance-compat"))
    problem_id = session.next_problem()
    assert problem_id is not None

    assert not asyncio.run(session.submit_answer(problem_id, "同义答案", 0.5))
    assert session.stats().total_count == 1
    session.close()
