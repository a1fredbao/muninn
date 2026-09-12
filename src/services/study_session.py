"""Output-free reciting session orchestration."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass

from ..core.base_plugin import BaseRecitePlugin
from ..core.scheduler import Scheduler
from ..core.state import StateManager


@dataclass(frozen=True)
class StudyStats:
    """Aggregate statistics for one study session."""

    distinct_ac: int
    total_problems: int
    ac_count: int
    total_count: int
    combo: int
    avg_time: float

    @property
    def accuracy(self) -> float:
        return self.ac_count / self.total_count if self.total_count else 0.0


class StudySession:
    """Own scheduling, answer judging, and persisted learning state."""

    def __init__(
        self,
        pack_id: str,
        plugin: BaseRecitePlugin,
        state_manager: StateManager | None = None,
    ) -> None:
        self.pack_id = pack_id
        self.plugin = plugin
        self.problem_ids = self.plugin.get_all_problem_ids()
        self.state_manager = state_manager or StateManager(pack_id)
        self.scheduler = Scheduler(self.problem_ids, self.state_manager)
        self.combo = 0
        self._closed = False

        self.distinct_ac = 0
        self.total_ac_count = 0
        self.total_count = 0
        self.total_ac_time = 0.0
        self._load_stats()

    def _load_stats(self) -> None:
        for problem_id in self.problem_ids:
            stats = self.state_manager.get_stats(problem_id)
            if stats["ac_count"] > 0:
                self.distinct_ac += 1
            self.total_ac_count += stats["ac_count"]
            self.total_count += stats["total_count"]
            self.total_ac_time += stats["total_ac_time"]

    def next_problem(self) -> str | None:
        return self.scheduler.next_problem()

    @property
    def async_judge(self) -> bool:
        return inspect.iscoroutinefunction(self.plugin.check_answer)

    def render_statement(self, problem_id: str) -> str:
        return self.plugin.render_statement(problem_id)

    async def submit_answer(
        self,
        problem_id: str,
        user_input: str,
        time_spent: float,
    ) -> bool:
        """Judge and record one answer without blocking the event loop."""

        matcher = self.plugin.check_answer
        if inspect.iscoroutinefunction(matcher):
            result = await matcher(problem_id, user_input)
        else:
            result = await asyncio.to_thread(matcher, problem_id, user_input)
            if inspect.isawaitable(result):
                result = await result

        is_correct = bool(result)
        self.total_count += 1
        self._record_result(problem_id, is_correct, time_spent)
        return is_correct

    def _record_result(
        self,
        problem_id: str,
        is_correct: bool,
        time_spent: float,
    ) -> None:
        stats = self.state_manager.get_stats(problem_id)
        if is_correct:
            if stats["ac_count"] == 0:
                self.distinct_ac += 1
            self.total_ac_count += 1
            self.combo += 1
            self.total_ac_time += time_spent
        else:
            self.combo = 0

        self.scheduler.update_problem(problem_id, is_correct, time_spent)

    def expected_answer(self, problem_id: str) -> str:
        return self.plugin.get_expected_display(problem_id)

    def expansion(self, problem_id: str) -> str:
        return self.plugin.get_expand_info(problem_id)

    def skip_problem(self, problem_id: str) -> None:
        """Remove a problem from the rest of this in-memory session."""

        if problem_id in self.problem_ids:
            self.problem_ids.remove(problem_id)
            self.scheduler.problem_ids.remove(problem_id)
            self.scheduler.q_queue = [
                item for item in self.scheduler.q_queue if item[1] != problem_id
            ]

    def stats(self) -> StudyStats:
        avg_time = (
            self.total_ac_time / self.total_ac_count
            if self.total_ac_count > 0
            else 0.0
        )
        return StudyStats(
            distinct_ac=self.distinct_ac,
            total_problems=len(self.problem_ids),
            ac_count=self.total_ac_count,
            total_count=self.total_count,
            combo=self.combo,
            avg_time=avg_time,
        )

    def close(self) -> None:
        if not self._closed:
            self.state_manager.close()
            self._closed = True

    @staticmethod
    def elapsed(start_time: float) -> float:
        return time.perf_counter() - start_time
