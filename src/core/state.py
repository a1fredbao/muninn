import os
import sqlite3
from typing import Any


class StateManager:
    def __init__(self, pack_id: str):
        self.pack_id = pack_id
        # ~/.muninn/states/
        self.state_dir = os.path.expanduser(os.path.join("~", ".muninn", "states"))
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

    def get_stats(self, problem_id: str) -> dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT ac_count, total_count, total_ac_time FROM problem_stats WHERE problem_id = ?",
            (problem_id,),
        )
        row = cursor.fetchone()
        if row:
            return {"ac_count": row[0], "total_count": row[1], "total_ac_time": row[2]}
        return {"ac_count": 0, "total_count": 0, "total_ac_time": 0.0}

    def update_stats(self, problem_id: str, is_ac: bool, time_spent: float):
        stats = self.get_stats(problem_id)

        new_total_count = stats["total_count"] + 1
        new_ac_count = stats["ac_count"] + (1 if is_ac else 0)
        new_total_ac_time = stats["total_ac_time"] + (time_spent if is_ac else 0.0)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO problem_stats (problem_id, ac_count, total_count, total_ac_time)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(problem_id) DO UPDATE SET
                ac_count = excluded.ac_count,
                total_count = excluded.total_count,
                total_ac_time = excluded.total_ac_time
        """,
            (problem_id, new_ac_count, new_total_count, new_total_ac_time),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
