import os
import sqlite3

from ..domain import AttemptOutcome, ProblemId, ProblemStats, ProgressAggregate


class StateManager:
    def __init__(self, pack_id: str, state_dir: str | None = None):
        self.pack_id = pack_id
        self.state_dir = state_dir or os.path.expanduser("~/.muninn/states")
        os.makedirs(self.state_dir, exist_ok=True)

        self.db_path = os.path.join(self.state_dir, f"{pack_id}.db")
        self.conn = sqlite3.connect(self.db_path)
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS problem_stats (
                problem_id TEXT PRIMARY KEY,
                ac_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0,
                total_ac_time REAL DEFAULT 0.0
            )
        """)
        self.conn.commit()

    def get_problem_stats(self, problem_id: ProblemId) -> ProblemStats:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT ac_count, total_count, total_ac_time FROM problem_stats WHERE problem_id = ?",
            (problem_id,),
        )
        row = cursor.fetchone()
        if row:
            return ProblemStats(
                ac_count=row[0],
                total_count=row[1],
                total_ac_time=row[2],
            )
        return ProblemStats()

    def get_stats(self, problem_id: str) -> dict[str, int | float]:
        """Backward-compatible dictionary form."""

        return self.get_problem_stats(ProblemId(problem_id)).as_dict()

    def record_attempt(self, outcome: AttemptOutcome) -> ProblemStats:
        """Record one attempt atomically and return the resulting statistics."""

        ac_increment = 1 if outcome.is_correct else 0
        time_increment = outcome.time_spent if outcome.is_correct else 0.0

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO problem_stats (
                    problem_id,
                    ac_count,
                    total_count,
                    total_ac_time
                )
                VALUES (?, ?, 1, ?)
                ON CONFLICT(problem_id) DO UPDATE SET
                    ac_count = problem_stats.ac_count + excluded.ac_count,
                    total_count = problem_stats.total_count + 1,
                    total_ac_time = problem_stats.total_ac_time + excluded.total_ac_time
                """,
                (
                    outcome.problem_id,
                    ac_increment,
                    time_increment,
                ),
            )
            row = self.conn.execute(
                """
                SELECT ac_count, total_count, total_ac_time
                FROM problem_stats
                WHERE problem_id = ?
                """,
                (outcome.problem_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError(
                f"Failed to read progress after recording '{outcome.problem_id}'."
            )
        return ProblemStats(
            ac_count=row[0],
            total_count=row[1],
            total_ac_time=row[2],
        )

    def update_stats(
        self,
        problem_id: str,
        is_ac: bool,
        time_spent: float,
    ) -> dict[str, int | float]:
        """Backward-compatible wrapper around :meth:`record_attempt`."""

        stats = self.record_attempt(
            AttemptOutcome(
                problem_id=ProblemId(problem_id),
                user_input="",
                is_correct=is_ac,
                time_spent=time_spent,
            )
        )
        return stats.as_dict()

    def aggregate(self, problem_ids: list[ProblemId]) -> ProgressAggregate:
        if not problem_ids:
            return ProgressAggregate(0, 0, 0, 0.0)

        active = set(problem_ids)
        cursor = self.conn.execute(
            "SELECT problem_id, ac_count, total_count, total_ac_time FROM problem_stats"
        )
        distinct_ac = 0
        ac_count = 0
        total_count = 0
        total_ac_time = 0.0
        for problem_id, item_ac, item_total, item_time in cursor:
            if problem_id not in active:
                continue
            if item_ac > 0:
                distinct_ac += 1
            ac_count += item_ac
            total_count += item_total
            total_ac_time += item_time
        return ProgressAggregate(
            distinct_ac=distinct_ac,
            ac_count=ac_count,
            total_count=total_count,
            total_ac_time=total_ac_time,
        )

    def migrate_problem_ids(self, id_map: dict[str, str]) -> int:
        """Merge legacy progress rows into stable IDs.

        If both IDs exist, their counters are combined. The legacy row is
        removed only after the destination row has been written.
        """

        migrated = 0
        with self.conn:
            for old_id, new_id in id_map.items():
                if old_id == new_id:
                    continue
                old_row = self.conn.execute(
                    """
                    SELECT ac_count, total_count, total_ac_time
                    FROM problem_stats
                    WHERE problem_id = ?
                    """,
                    (old_id,),
                ).fetchone()
                if old_row is None:
                    continue

                self.conn.execute(
                    """
                    INSERT INTO problem_stats (
                        problem_id,
                        ac_count,
                        total_count,
                        total_ac_time
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(problem_id) DO UPDATE SET
                        ac_count = problem_stats.ac_count + excluded.ac_count,
                        total_count = problem_stats.total_count + excluded.total_count,
                        total_ac_time = problem_stats.total_ac_time + excluded.total_ac_time
                    """,
                    (new_id, old_row[0], old_row[1], old_row[2]),
                )
                self.conn.execute(
                    "DELETE FROM problem_stats WHERE problem_id = ?",
                    (old_id,),
                )
                migrated += 1
        return migrated

    def close(self):
        self.conn.close()
