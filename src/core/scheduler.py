import heapq
import random

from .state import StateManager


class Scheduler:
    def __init__(self, problem_ids: list[str], state_manager: StateManager):
        self.problem_ids = problem_ids
        self.state_manager = state_manager
        self.q_queue = []
        self._init_queue()

    def _calculate_weight(self, problem_id: str) -> float:
        stats = self.state_manager.get_stats(problem_id)
        ac_count = stats["ac_count"]
        total_count = stats["total_count"]
        total_ac_time = stats["total_ac_time"]

        ac_ratio = ac_count / total_count if total_count > 0 else 0
        avg_time = total_ac_time / ac_count if ac_count > 0 else 10.0

        # Smart weight: higher ac_count & ratio -> lower weight (less likely)
        # Higher avg_time -> higher weight
        return random.random() - ac_count - 10.0 * ac_ratio + avg_time

    def _init_queue(self):
        for pid in self.problem_ids:
            weight = self._calculate_weight(pid)
            # heapq is a min-heap, so we push negative weight to pop the max weight
            heapq.heappush(self.q_queue, (-weight, pid))

    def next_problem(self) -> str:
        """Returns the ID of the next problem to display."""
        if not self.q_queue:
            return None
        _, pid = heapq.heappop(self.q_queue)
        return pid

    def update_problem(self, problem_id: str, is_ac: bool, time_spent: float):
        """Updates the state and pushes the problem back into the queue."""
        self.state_manager.update_stats(problem_id, is_ac, time_spent)
        weight = self._calculate_weight(problem_id)
        heapq.heappush(self.q_queue, (-weight, problem_id))
