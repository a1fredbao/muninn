"""Training-attempt orchestration independent of the terminal UI."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..core.progress import ProgressStore
from ..core.scheduler import Scheduler
from ..domain import AttemptOutcome, AttemptResult, ProblemId, ProblemRef


@dataclass(frozen=True, slots=True)
class AnswerEvaluation:
    """Result of the non-interactive part of answer evaluation."""

    is_correct: bool
    needs_user_acceptance: bool = False
    user_confirmed: bool = False


def answer_key(user_input: str) -> str:
    """Stable key for persisting a user's acceptance decision."""

    return "".join(user_input.split()).casefold()


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

    def _problem(self, problem_id: ProblemId) -> tuple[Any, ProblemRef]:
        try:
            return self.problems[problem_id]
        except KeyError as exc:
            raise KeyError(f"Unknown problem: {problem_id}") from exc

    async def evaluate_answer(
        self,
        problem_id: ProblemId,
        user_input: str,
    ) -> AnswerEvaluation:
        plugin, problem = self._problem(problem_id)
        if bool(await plugin.check_answer(problem, user_input)):
            return AnswerEvaluation(True)

        key = answer_key(user_input)
        decision = self.progress_store.get_answer_decision(problem_id, key)
        if decision is not None:
            return AnswerEvaluation(decision, user_confirmed=True)

        supports = getattr(plugin, "supports_user_acceptance", None)
        if supports is not None:
            allowed = supports(problem)
            if inspect.isawaitable(allowed):
                allowed = await allowed
            if allowed:
                return AnswerEvaluation(False, needs_user_acceptance=True)

        return AnswerEvaluation(False)

    def record_evaluation(
        self,
        problem_id: ProblemId,
        user_input: str,
        time_spent: float,
        evaluation: AnswerEvaluation,
    ) -> AttemptResult:
        outcome = AttemptOutcome(
            problem_id=problem_id,
            user_input=user_input,
            is_correct=evaluation.is_correct,
            time_spent=max(0.0, time_spent),
            user_confirmed=evaluation.user_confirmed,
        )
        stats = self.progress_store.record_attempt(outcome)
        self.scheduler.refresh_problem(problem_id)
        return AttemptResult(outcome=outcome, stats=stats)

    def record_user_decision(
        self,
        problem_id: ProblemId,
        user_input: str,
        time_spent: float,
        accepted: bool,
    ) -> AttemptResult:
        self.progress_store.record_answer_decision(
            problem_id,
            answer_key(user_input),
            accepted,
        )
        return self.record_evaluation(
            problem_id,
            user_input,
            time_spent,
            AnswerEvaluation(accepted, user_confirmed=True),
        )
