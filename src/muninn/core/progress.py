"""Persistence interface consumed by the training session."""

from __future__ import annotations

from typing import Protocol

from ..domain import AttemptOutcome, ProblemId, ProblemStats, ProgressAggregate


class ProgressStore(Protocol):
    """Narrow storage contract for attempts and problem progress."""

    def get_problem_stats(self, problem_id: ProblemId) -> ProblemStats: ...

    def record_attempt(self, outcome: AttemptOutcome) -> ProblemStats: ...

    def aggregate(self, problem_ids: list[ProblemId]) -> ProgressAggregate: ...

    def migrate_problem_ids(self, id_map: dict[str, str]) -> int: ...

    def close(self) -> None: ...
