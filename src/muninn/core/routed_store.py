"""Progress-store router for sessions containing multiple packs."""

from __future__ import annotations

from ..domain import (
    AttemptOutcome,
    ProblemId,
    ProblemStats,
    ProgressAggregate,
)
from .state import StateManager


class RoutedProgressStore:
    """Route global problem IDs to the owning pack's progress database."""

    def __init__(self, state_dir: str | None = None) -> None:
        self.state_dir = state_dir
        self._stores: dict[str, StateManager] = {}
        self._routes: dict[ProblemId, tuple[str, ProblemId]] = {}

    def register(
        self,
        global_id: ProblemId,
        pack_id: str,
        local_id: ProblemId,
    ) -> None:
        if global_id in self._routes:
            raise ValueError(f"Duplicate global problem ID: {global_id}")
        self._routes[global_id] = (pack_id, local_id)
        if pack_id not in self._stores:
            self._stores[pack_id] = StateManager(pack_id, self.state_dir)

    def _route(self, problem_id: ProblemId) -> tuple[StateManager, ProblemId]:
        try:
            pack_id, local_id = self._routes[problem_id]
        except KeyError as exc:
            raise KeyError(f"Unknown global problem ID: {problem_id}") from exc
        return self._stores[pack_id], local_id

    def get_problem_stats(self, problem_id: ProblemId) -> ProblemStats:
        store, local_id = self._route(problem_id)
        return store.get_problem_stats(local_id)

    def record_attempt(self, outcome: AttemptOutcome) -> ProblemStats:
        store, local_id = self._route(outcome.problem_id)
        return store.record_attempt(
            AttemptOutcome(
                problem_id=local_id,
                user_input=outcome.user_input,
                is_correct=outcome.is_correct,
                time_spent=outcome.time_spent,
            )
        )

    def aggregate(self, problem_ids: list[ProblemId]) -> ProgressAggregate:
        ids_by_pack: dict[str, list[ProblemId]] = {}
        for problem_id in problem_ids:
            store, local_id = self._route(problem_id)
            del store
            pack_id = self._routes[problem_id][0]
            ids_by_pack.setdefault(pack_id, []).append(local_id)

        distinct_ac = 0
        ac_count = 0
        total_count = 0
        total_ac_time = 0.0
        for pack_id, local_ids in ids_by_pack.items():
            aggregate = self._stores[pack_id].aggregate(local_ids)
            distinct_ac += aggregate.distinct_ac
            ac_count += aggregate.ac_count
            total_count += aggregate.total_count
            total_ac_time += aggregate.total_ac_time
        return ProgressAggregate(
            distinct_ac=distinct_ac,
            ac_count=ac_count,
            total_count=total_count,
            total_ac_time=total_ac_time,
        )

    def migrate_problem_ids(self, id_map: dict[str, str]) -> int:
        del id_map
        return 0

    def close(self) -> None:
        for store in self._stores.values():
            store.close()
        self._stores.clear()
