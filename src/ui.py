import os
import sys


class TerminalUI:
    # -- screen buffer -------------------------------------------------------

    @staticmethod
    def enter_alt_screen():
        """Switch to the alternate screen buffer.

        All subsequent output goes to a fresh canvas.  When
        ``exit_alt_screen()`` is called, the original terminal content
        (shell history, previous commands) is restored exactly as it was.

        Works on virtually every modern terminal (xterm, iTerm2, Windows
        Terminal, etc.).  Gracefully degrades to a no-op on terminals
        that don't support it.
        """
        sys.stdout.write("\033[?1049h")
        sys.stdout.flush()

    @staticmethod
    def exit_alt_screen():
        """Restore the main screen buffer, bringing back the original
        terminal content."""
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

    # -- drawing helpers -----------------------------------------------------

    @staticmethod
    def clear_screen():
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def wait_any_key():
        input("按回车键继续...")

    @staticmethod
    def print_cyan(text: str):
        print(f"\033[36;1m{text}\033[0m")

    @staticmethod
    def print_green(text: str):
        print(f"\033[32m{text}\033[0m")

    @staticmethod
    def print_yellow(text: str):
        print(f"\033[33;1m{text}\033[0m")

    @staticmethod
    def print_success_banner(time_spent: float):
        print(f"\n\033[42;37;1m Accepted \033[0m 耗时: {time_spent:.2f} 秒")

    @staticmethod
    def print_error_banner():
        print("\n\033[41;37;1m Wrong Answer \033[0m")

    @staticmethod
    def print_stats_banner(
        distinct_ac: int,
        total_problems: int,
        ac_count: int,
        total_count: int,
        combo: int,
        avg_time: float,
    ):
        print(
            f"掌握题数: {distinct_ac} / {total_problems}\t"
            f"总正确率: {ac_count} / {total_count}\t"
            f"Combo: {combo}\t"
            f"平均用时: {avg_time:.2f}s\n"
        )
