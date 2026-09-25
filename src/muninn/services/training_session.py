"""Output-free training session orchestration."""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass

from ..core.progress import ProgressStore
from ..core.scheduler import Scheduler
from ..core.state import StateManager
from ..domain import ProblemId
from ..plugin_api import Plugin
from .training import TrainingCoordinator


@dataclass(frozen=True)
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


class TrainingSession:
    """Own scheduling, answer judging, and persisted training state."""

    def __init__(
        self,
        pack_id: str,
        plugin: Plugin,
        progress_store: ProgressStore,
        scheduler: Scheduler,
    ) -> None:
        self.pack_id = pack_id
        self.plugin = plugin
        self.progress_store = progress_store
        self.scheduler = scheduler
        self.training_coordinator = TrainingCoordinator(
            plugin,
            progress_store,
            scheduler,
        )
        self.combo = 0
        self._closed = False
        self._progress = self.progress_store.aggregate(
            self.scheduler.active_problem_ids
        )

    @classmethod
    async def create(
        cls,
        pack_id: str,
        plugin: Plugin,
        progress_store: ProgressStore | None = None,
    ) -> TrainingSession:
        owns_store = progress_store is None
        store = progress_store or StateManager(pack_id)
        try:
            problem_ids = await plugin.get_all_problem_ids()
            legacy_map_method = getattr(plugin, "legacy_problem_id_map", None)
            if legacy_map_method is not None:
                id_map = legacy_map_method()
                if inspect.isawaitable(id_map):
                    id_map = await id_map
                if id_map:
                    store.migrate_problem_ids(id_map)
            scheduler = Scheduler(
                [str(problem_id) for problem_id in problem_ids],
                store,
            )
            return cls(pack_id, plugin, store, scheduler)
        except Exception:
            if owns_store:
                store.close()
            raise

    def next_problem(self) -> ProblemId | None:
        return self.scheduler.next_problem()

    async def render_statement(self, problem_id: str) -> str:
        result = await self.plugin.render_statement(problem_id)
        return str(result)

    async def submit_answer(
        self,
        problem_id: str,
        user_input: str,
        time_spent: float,
    ) -> bool:
        """Judge and record one answer without blocking the event loop."""

        result = await self.training_coordinator.record_attempt(
            ProblemId(problem_id),
            user_input,
            time_spent,
        )
        if result.outcome.is_correct:
            self.combo += 1
        else:
            self.combo = 0
        self._progress = self.progress_store.aggregate(
            self.scheduler.active_problem_ids
        )
        return result.outcome.is_correct

    async def expected_answer(self, problem_id: str) -> str:
        return str(await self.plugin.get_expected_display(problem_id))

    async def expansion(self, problem_id: str) -> str:
        result = await self.plugin.get_expand_info(problem_id)
        return "" if result is None else str(result)

    def skip_problem(self, problem_id: str) -> None:
        """Remove a problem from the rest of this in-memory session."""

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
        if not self._closed:
            try:
                close = getattr(self.plugin, "close", None)
                if close is not None:
                    close()
            finally:
                self.progress_store.close()
            self._closed = True

    async def aclose(self) -> None:
        if self._closed:
            return
        try:
            close = getattr(self.plugin, "aclose", None)
            if close is not None:
                await close()
            else:
                self.plugin.close()
        finally:
            self.progress_store.close()
        self._closed = True

    @staticmethod
    def elapsed(start_time: float) -> float:
        return time.perf_counter() - start_time
