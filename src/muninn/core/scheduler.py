"""Problem queue and scheduling policy."""

from __future__ import annotations

import heapq
import random
from collections.abc import Callable
from typing import Protocol

from ..domain import ProblemId, ProblemStats
from .progress import ProgressStore


class SchedulingPolicy(Protocol):
    """Compute a score where larger values are selected first."""

    def score(self, problem_id: ProblemId, stats: ProblemStats) -> float: ...


class WeightedTrainingPolicy:
    """A bounded heuristic that favours weak and slower problems.

    The score is normalized so long-lived problems cannot dominate solely
    because they have a large cumulative answer count.
    """

    def __init__(
        self,
        *,
        random_value: Callable[[], float] = random.random,
        max_attempt_weight: int = 10,
        max_time_weight: float = 60.0,
    ) -> None:
        self._random_value = random_value
        self.max_attempt_weight = max_attempt_weight
        self.max_time_weight = max_time_weight

    def score(self, problem_id: ProblemId, stats: ProblemStats) -> float:
        del problem_id
        attempt_factor = min(stats.total_count, self.max_attempt_weight) / max(
            self.max_attempt_weight,
            1,
        )
        average_time = stats.average_ac_time if stats.ac_count else self.max_time_weight
        time_factor = min(average_time, self.max_time_weight) / self.max_time_weight
        mastery = stats.accuracy * attempt_factor
        return (
            (1.0 - mastery) * 2.0
            + (1.0 - stats.accuracy) * 2.0
            + time_factor
            + self._random_value() * 0.25
        )


class Scheduler:
    def __init__(
        self,
        problem_ids: list[str],
        progress_store: ProgressStore,
        policy: SchedulingPolicy | None = None,
    ):
        self.active_problem_ids = [ProblemId(problem_id) for problem_id in problem_ids]
        self.progress_store = progress_store
        self.policy = policy or WeightedTrainingPolicy()
        self.q_queue: list[tuple[float, ProblemId]] = []
        self._init_queue()

    def _get_stats(self, problem_id: ProblemId) -> ProblemStats:
        getter = getattr(self.progress_store, "get_problem_stats", None)
        if getter is not None:
            return getter(problem_id)
        raw = self.progress_store.get_stats(problem_id)
        return ProblemStats(
            ac_count=raw["ac_count"],
            total_count=raw["total_count"],
            total_ac_time=raw["total_ac_time"],
        )

    def _calculate_weight(self, problem_id: ProblemId) -> float:
        return self.policy.score(problem_id, self._get_stats(problem_id))

    def _init_queue(self) -> None:
        for problem_id in self.active_problem_ids:
            weight = self._calculate_weight(problem_id)
            heapq.heappush(self.q_queue, (-weight, problem_id))

    def next_problem(self) -> ProblemId | None:
        """Return the ID of the next problem to display."""

        if not self.q_queue:
            return None
        _, problem_id = heapq.heappop(self.q_queue)
        return problem_id

    def refresh_problem(self, problem_id: str) -> None:
        """Push a problem back using its latest persisted statistics."""

        typed_id = ProblemId(problem_id)
        if typed_id not in self.active_problem_ids:
            return
        weight = self._calculate_weight(typed_id)
        heapq.heappush(self.q_queue, (-weight, typed_id))

    def update_problem(
        self,
        problem_id: str,
        is_ac: bool,
        time_spent: float,
    ) -> None:
        """Compatibility wrapper that only requeues the problem.

        Persistence now belongs to ``TrainingCoordinator``. This method is
        retained for callers that only need to manipulate the queue.
        """

        del is_ac, time_spent
        self.refresh_problem(problem_id)

    def remove_problem(self, problem_id: str) -> bool:
        """Remove a problem from the active session and pending queue."""

        typed_id = ProblemId(problem_id)
        if typed_id not in self.active_problem_ids:
            return False

        self.active_problem_ids.remove(typed_id)
        self.q_queue = [item for item in self.q_queue if item[1] != typed_id]
        heapq.heapify(self.q_queue)
        return True
