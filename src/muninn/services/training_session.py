"""Output-free training session orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..core.progress import ProgressStore
from ..core.routed_store import RoutedProgressStore
from ..core.scheduler import Scheduler
from ..domain import (
    ProblemId,
    ProblemRef,
    SchedulingContext,
)
from ..keys import pack_key as make_pack_key
from ..keys import problem_key as make_problem_key
from ..keys import question_type_key as make_question_type_key
from .training import TrainingCoordinator


@dataclass(frozen=True, slots=True)
class QuestionRoute:
    """One selected question type backed by a loaded plugin adapter."""

    pack_id: str
    question_type_id: str
    plugin: Any
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class TrainingStats:
    """Aggregate statistics for one training session."""

    distinct_ac: int
    total_problems: int
    ac_count: int
    total_count: int
    combo: int
    avg_time: float

    @property
    def accuracy(self) -> float:
        return self.ac_count / self.total_count if self.total_count else 0.0


@dataclass(slots=True)
class _PreparedProblem:
    ref: ProblemRef
    plugin: Any


class TrainingSession:
    """Own scheduling, answer judging, and persisted training state."""

    def __init__(
        self,
        routes: list[QuestionRoute],
        problems: list[_PreparedProblem],
        progress_store: ProgressStore,
        scheduler: Scheduler,
    ) -> None:
        self.routes = routes
        self.problems = {problem.ref.key: problem for problem in problems}
        self.progress_store = progress_store
        self.scheduler = scheduler
        self.training_coordinator = TrainingCoordinator(
            {problem.ref.key: (problem.plugin, problem.ref) for problem in problems},
            progress_store,
            scheduler,
        )
        self.combo = 0
        self.warnings: tuple[str, ...] = ()
        self._closed = False
        self._progress = self.progress_store.aggregate(
            self.scheduler.active_problem_ids
        )

    @classmethod
    async def create(
        cls,
        routes: list[QuestionRoute],
        *,
        state_dir: str | None = None,
    ) -> TrainingSession:
        if not routes:
            raise ValueError("A training session requires at least one question type.")

        progress_store = RoutedProgressStore(state_dir)
        prepared: list[_PreparedProblem] = []
        contexts: dict[ProblemId, SchedulingContext] = {}
        try:
            for route in routes:
                question_type_key = make_question_type_key(
                    route.pack_id,
                    route.question_type_id,
                )
                for local_problem_id in await route.plugin.get_all_problem_ids(
                    _temporary_ref(route)
                ):
                    global_id = make_problem_key(
                        route.pack_id,
                        route.question_type_id,
                        local_problem_id,
                    )
                    ref = ProblemRef(
                        key=ProblemId(global_id),
                        pack_id=route.pack_id,
                        pack_key=make_pack_key(route.pack_id),
                        question_type_id=route.question_type_id,
                        question_type_key=question_type_key,
                        local_problem_id=local_problem_id,
                    )
                    progress_store.register(
                        ref.key,
                        route.pack_id,
                        ProblemId(local_problem_id),
                    )
                    metadata = await route.plugin.describe_problem(ref)
                    contexts[ref.key] = SchedulingContext(
                        selection_weight=route.weight,
                        metadata=metadata,
                    )
                    prepared.append(_PreparedProblem(ref=ref, plugin=route.plugin))

            scheduler = Scheduler(
                [problem.ref for problem in prepared],
                progress_store,
                contexts=contexts,
            )
            return cls(routes, prepared, progress_store, scheduler)
        except Exception:
            progress_store.close()
            raise

    def next_problem(self) -> ProblemId | None:
        return self.scheduler.next_problem()

    def _problem(self, problem_id: str) -> _PreparedProblem:
        try:
            return self.problems[ProblemId(problem_id)]
        except KeyError as exc:
            raise KeyError(f"Unknown problem ID: {problem_id}") from exc

    async def render_statement(self, problem_id: str) -> str:
        problem = self._problem(problem_id)
        result = await problem.plugin.render_statement(problem.ref)
        return str(result)

    async def submit_answer(
        self,
        problem_id: str,
        user_input: str,
        time_spent: float,
    ) -> bool:
        result = await self.training_coordinator.record_attempt(
            ProblemId(problem_id),
            user_input,
            time_spent,
        )
        self.combo = self.combo + 1 if result.outcome.is_correct else 0
        self._progress = self.progress_store.aggregate(
            self.scheduler.active_problem_ids
        )
        return result.outcome.is_correct

    async def expected_answer(self, problem_id: str) -> str:
        problem = self._problem(problem_id)
        return str(await problem.plugin.get_expected_display(problem.ref))

    async def expansion(self, problem_id: str) -> str:
        problem = self._problem(problem_id)
        result = await problem.plugin.get_expand_info(problem.ref)
        return "" if result is None else str(result)

    def skip_problem(self, problem_id: str) -> None:
        self.scheduler.remove_problem(problem_id)

    def stats(self) -> TrainingStats:
        return TrainingStats(
            distinct_ac=self._progress.distinct_ac,
            total_problems=len(self.scheduler.active_problem_ids),
            ac_count=self._progress.ac_count,
            total_count=self._progress.total_count,
            combo=self.combo,
            avg_time=self._progress.average_ac_time,
        )

    def close(self) -> None:
        if self._closed:
            return
        try:
            for route in self.routes:
                close = getattr(route.plugin, "close", None)
                if close is not None:
                    close()
        finally:
            self.progress_store.close()
        self._closed = True

    async def aclose(self) -> None:
        if self._closed:
            return
        try:
            for route in self.routes:
                close = getattr(route.plugin, "aclose", None)
                if close is not None:
                    await close()
                else:
                    route.plugin.close()
        finally:
            self.progress_store.close()
        self._closed = True

    @staticmethod
    def elapsed(start_time: float) -> float:
        return time.perf_counter() - start_time


def _temporary_ref(route: QuestionRoute) -> ProblemRef:
    """Create a type-level ref used only for the list-problems adapter call."""

    return ProblemRef(
        key=ProblemId(""),
        pack_id=route.pack_id,
        pack_key=make_pack_key(route.pack_id),
        question_type_id=route.question_type_id,
        question_type_key=make_question_type_key(
            route.pack_id,
            route.question_type_id,
        ),
        local_problem_id="",
    )
