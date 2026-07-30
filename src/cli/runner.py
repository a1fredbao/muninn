import sys
import time

from ..core.base_plugin import BaseRecitePlugin
from ..core.scheduler import Scheduler
from ..core.state import StateManager
from ..ui import TerminalUI


class GameRunner:
    def __init__(self, pack_id: str, plugin: BaseRecitePlugin):
        self.pack_id = pack_id
        self.plugin = plugin

        self.problem_ids = self.plugin.get_all_problem_ids()
        self.state_manager = StateManager(pack_id)
        self.scheduler = Scheduler(self.problem_ids, self.state_manager)

        self.combo = 0

        # Calculate distinct AC count across all problems at startup
        self.distinct_ac = 0
        self.total_ac_count = 0
        self.total_count = 0
        self.total_ac_time = 0.0

        for pid in self.problem_ids:
            stats = self.state_manager.get_stats(pid)
            if stats["ac_count"] > 0:
                self.distinct_ac += 1
            self.total_ac_count += stats["ac_count"]
            self.total_count += stats["total_count"]
            self.total_ac_time += stats["total_ac_time"]

    def run(self):
        TerminalUI.enter_alt_screen()
        TerminalUI.clear_screen()
        TerminalUI.print_green(f"====== 正在学习包: {self.pack_id} ======\n")
        TerminalUI.wait_any_key()

        try:
            while True:
                problem_id = self.scheduler.next_problem()
                if not problem_id:
                    print("题库为空！")
                    break
                self.ask(problem_id)
        except (KeyboardInterrupt, EOFError):
            self.quit()

    def ask(self, problem_id: str):
        TerminalUI.clear_screen()

        avg_time = (
            self.total_ac_time / self.total_ac_count if self.total_ac_count > 0 else 0
        )
        TerminalUI.print_stats_banner(
            distinct_ac=self.distinct_ac,
            total_problems=len(self.problem_ids),
            ac_count=self.total_ac_count,
            total_count=self.total_count,
            combo=self.combo,
            avg_time=avg_time,
        )

        statement = self.plugin.render_statement(problem_id)
        TerminalUI.print_cyan(statement)
        print("（输入 q 退出）")

        start_time = time.perf_counter()
        user_input = input(">> ").strip()

        if user_input.lower() == "q":
            self.quit()

        end_time = time.perf_counter()
        time_spent = end_time - start_time

        self.total_count += 1

        is_correct = self.plugin.check_answer(problem_id, user_input)

        if is_correct:
            self._handle_ac(problem_id, time_spent)
        else:
            self._handle_wa(problem_id)

        self.scheduler.update_problem(problem_id, is_correct, time_spent)

    def _handle_ac(self, problem_id: str, time_spent: float):
        stats = self.state_manager.get_stats(problem_id)
        if stats["ac_count"] == 0:
            self.distinct_ac += 1

        self.total_ac_count += 1
        self.combo += 1
        self.total_ac_time += time_spent

        TerminalUI.print_success_banner(time_spent)
        expand_info = self.plugin.get_expand_info(problem_id)
        if expand_info:
            print(f"💡 拓展信息: {expand_info}\n")

        TerminalUI.wait_any_key()

    def _handle_wa(self, problem_id: str):
        self.combo = 0
        TerminalUI.print_error_banner()
        expected = self.plugin.get_expected_display(problem_id)
        print(f"标准答案: \033[33;1m{expected}\033[0m\n")
        TerminalUI.wait_any_key()

    def quit(self):
        TerminalUI.exit_alt_screen()
        print("=== 学习统计 ===")
        print(f"总答题数: {self.total_count}")
        if self.total_count > 0:
            print(
                f"总正确率: {self.total_ac_count} / {self.total_count} ({self.total_ac_count / self.total_count * 100:.1f}%)"
            )
        self.state_manager.close()
        sys.exit(0)
