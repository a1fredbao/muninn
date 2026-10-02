"""Tests for scheduling candidates and queue behavior."""

from muninn.core.scheduler import Scheduler, WeightedTrainingPolicy
from muninn.domain import (
    ProblemId,
    ProblemMetadata,
    ProblemRef,
    ProblemStats,
    SchedulingCandidate,
    SchedulingContext,
)


def _ref(problem_id: str) -> ProblemRef:
    return ProblemRef(
        key=ProblemId(f"global-{problem_id}"),
        pack_id="pack",
        pack_key="pack_hash",
        question_type_id="type",
        question_type_key="type_hash",
        local_problem_id=problem_id,
    )


def _candidate(
    problem_id: str,
    stats: ProblemStats,
) -> SchedulingCandidate:
    return SchedulingCandidate(
        problem=_ref(problem_id),
        stats=stats,
        context=SchedulingContext(
            selection_weight=1.0,
            metadata=ProblemMetadata(),
        ),
    )


class TestScheduler:
    def test_queue_initialized_with_all_problems(self, mock_state_manager):
        problems = [_ref(value) for value in ("a", "b", "c", "d", "e")]
        scheduler = Scheduler(problems, mock_state_manager)
        assert len(scheduler.q_queue) == 5
        assert scheduler.active_problem_ids == [problem.key for problem in problems]

    def test_next_problem_returns_valid_id(self, mock_state_manager):
        problems = [_ref(value) for value in ("a", "b", "c")]
        scheduler = Scheduler(problems, mock_state_manager)
        assert scheduler.next_problem() in {problem.key for problem in problems}

    def test_update_puts_problem_back(self, mock_state_manager):
        problems = [_ref(value) for value in ("a", "b", "c")]
        scheduler = Scheduler(problems, mock_state_manager)
        for _ in range(3):
            scheduler.next_problem()
        assert scheduler.next_problem() is None

        scheduler.update_problem(problems[0].key, is_ac=True, time_spent=3.0)
        assert scheduler.next_problem() == problems[0].key

    def test_remove_queued_problem(self, mock_state_manager):
        problems = [_ref(value) for value in ("a", "b", "c")]
        scheduler = Scheduler(problems, mock_state_manager)

        assert scheduler.remove_problem(problems[1].key)
        assert scheduler.active_problem_ids == [problems[0].key, problems[2].key]
        assert all(item[1] != problems[1].key for item in scheduler.q_queue)
        assert not scheduler.remove_problem(problems[1].key)

    def test_bounded_policy_does_not_let_attempt_count_dominate(self):
        policy = WeightedTrainingPolicy(random_value=lambda: 0.0)
        mastered = policy.score(
            _candidate(
                "mastered",
                ProblemStats(
                    ac_count=1000,
                    total_count=1000,
                    total_ac_time=1.0,
                ),
            )
        )
        weak = policy.score(
            _candidate(
                "weak",
                ProblemStats(ac_count=0, total_count=1, total_ac_time=0.0),
            )
        )
        assert weak > mastered

    def test_policy_uses_plugin_metadata_and_selection_weight(self):
        policy = WeightedTrainingPolicy(random_value=lambda: 0.0)
        easy = SchedulingCandidate(
            problem=_ref("easy"),
            stats=ProblemStats(),
            context=SchedulingContext(
                selection_weight=1.0,
                metadata=ProblemMetadata(difficulty=0.1),
            ),
        )
        hard = SchedulingCandidate(
            problem=_ref("hard"),
            stats=ProblemStats(),
            context=SchedulingContext(
                selection_weight=2.0,
                metadata=ProblemMetadata(difficulty=0.9),
            ),
        )

        assert policy.score(hard) > policy.score(easy)
