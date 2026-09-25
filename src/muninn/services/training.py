"""Training-attempt orchestration independent of the terminal UI."""

from __future__ import annotations

from ..core.progress import ProgressStore
from ..core.scheduler import Scheduler
from ..domain import AttemptOutcome, AttemptResult, ProblemId
from ..plugin_api import Plugin


class TrainingCoordinator:
    """Judge one answer and commit its progress through one code path."""

    def __init__(
        self,
        plugin: Plugin,
        progress_store: ProgressStore,
        scheduler: Scheduler,
    ) -> None:
        self.plugin = plugin
        self.progress_store = progress_store
        self.scheduler = scheduler

    async def record_attempt(
        self,
        problem_id: ProblemId,
        user_input: str,
        time_spent: float,
    ) -> AttemptResult:
        raw_result = await self.plugin.check_answer(problem_id, user_input)
        outcome = AttemptOutcome(
            problem_id=problem_id,
            user_input=user_input,
            is_correct=bool(raw_result),
            time_spent=max(0.0, time_spent),
        )
        stats = self.progress_store.record_attempt(outcome)
        self.scheduler.refresh_problem(problem_id)
        return AttemptResult(outcome=outcome, stats=stats)
