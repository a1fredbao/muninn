"""Tests for src/core/scheduler.py."""

from muninn.core.scheduler import Scheduler, WeightedTrainingPolicy
from muninn.domain import ProblemStats


class TestScheduler:
    def test_queue_initialized_with_all_problems(self, mock_state_manager):
        ids = ["a", "b", "c", "d", "e"]
        s = Scheduler(ids, mock_state_manager)
        assert len(s.q_queue) == 5
        assert s.active_problem_ids == ids
        assert s.active_problem_ids is not ids

    def test_next_problem_returns_valid_id(self, mock_state_manager):
        ids = ["a", "b", "c"]
        s = Scheduler(ids, mock_state_manager)
        pid = s.next_problem()
        assert pid in ids

    def test_next_problem_removes_from_queue(self, mock_state_manager):
        ids = ["a", "b", "c"]
        s = Scheduler(ids, mock_state_manager)
        initial = len(s.q_queue)
        s.next_problem()
        assert len(s.q_queue) == initial - 1

    def test_update_puts_problem_back(self, mock_state_manager):
        ids = ["a", "b", "c"]
        s = Scheduler(ids, mock_state_manager)
        for _ in range(3):
            s.next_problem()
        # Queue should be empty
        assert s.next_problem() is None
        # Push one back
        s.update_problem("a", is_ac=True, time_spent=3.0)
        assert s.next_problem() == "a"

    def test_all_problems_eventually_returned(self, mock_state_manager):
        """Drain-and-refill: all problem IDs should appear after enough cycles."""
        ids = ["a", "b"]
        s = Scheduler(ids, mock_state_manager)

        # Drain the queue first
        drained = []
        while True:
            pid = s.next_problem()
            if pid is None:
                break
            drained.append(pid)
        assert len(drained) == 2

        # Refill with all
        for pid in drained:
            s.update_problem(pid, is_ac=True, time_spent=1.0)

        # Drain again
        redrained = {s.next_problem(), s.next_problem()}
        assert redrained == {"a", "b"}

    def test_empty_ids(self, mock_state_manager):
        s = Scheduler([], mock_state_manager)
        assert s.next_problem() is None

    def test_remove_queued_problem(self, mock_state_manager):
        s = Scheduler(["a", "b", "c"], mock_state_manager)

        assert s.remove_problem("b")
        assert s.active_problem_ids == ["a", "c"]
        assert all(item[1] != "b" for item in s.q_queue)
        assert not s.remove_problem("b")

        remaining = set()
        while (problem_id := s.next_problem()) is not None:
            remaining.add(problem_id)
        assert remaining == {"a", "c"}

    def test_removed_problem_is_not_requeued(self, mock_state_manager):
        s = Scheduler(["a", "b"], mock_state_manager)
        problem_id = s.next_problem()
        assert problem_id is not None

        assert s.remove_problem(problem_id)
        s.update_problem(problem_id, is_ac=True, time_spent=1.0)

        remaining = set()
        while (next_problem := s.next_problem()) is not None:
            remaining.add(next_problem)
        assert problem_id not in remaining

    def test_bounded_policy_does_not_let_attempt_count_dominate(self):
        policy = WeightedTrainingPolicy(random_value=lambda: 0.0)
        mastered = policy.score(
            "mastered",
            ProblemStats(ac_count=1000, total_count=1000, total_ac_time=1.0),
        )
        weak = policy.score(
            "weak",
            ProblemStats(ac_count=0, total_count=1, total_ac_time=0.0),
        )
        assert weak > mastered
