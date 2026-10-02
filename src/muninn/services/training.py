"""Training-attempt orchestration independent of the terminal UI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.progress import ProgressStore
from ..core.scheduler import Scheduler
from ..domain import AttemptOutcome, AttemptResult, ProblemId, ProblemRef


class TrainingCoordinator:
    """Judge one answer and commit its progress through one code path."""

    def __init__(
        self,
        problems: Mapping[ProblemId, tuple[Any, ProblemRef]],
        progress_store: ProgressStore,
        scheduler: Scheduler,
    ) -> None:
        self.problems = dict(problems)
        self.progress_store = progress_store
        self.scheduler = scheduler

    async def record_attempt(
        self,
        problem_id: ProblemId,
        user_input: str,
        time_spent: float,
    ) -> AttemptResult:
        try:
            plugin, problem = self.problems[problem_id]
        except KeyError as exc:
            raise KeyError(f"Unknown problem: {problem_id}") from exc
        raw_result = await plugin.check_answer(problem, user_input)
        outcome = AttemptOutcome(
            problem_id=problem_id,
            user_input=user_input,
            is_correct=bool(raw_result),
            time_spent=max(0.0, time_spent),
        )
        stats = self.progress_store.record_attempt(outcome)
        self.scheduler.refresh_problem(problem_id)
        return AttemptResult(outcome=outcome, stats=stats)
