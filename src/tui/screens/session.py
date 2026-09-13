"""Interactive reciting session screen."""

from __future__ import annotations

import asyncio
import time
from typing import ClassVar

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, LoadingIndicator, Static

from ...services.study_session import StudySession
from .dialogs import JudgeErrorDialog, SessionSummaryDialog


class SessionScreen(Screen[None]):
    """Ask questions while keeping the Textual event loop responsive."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "leave", "Library", show=True),
        Binding("enter", "next_problem", "Next", show=True),
    ]

    def __init__(self, session: StudySession) -> None:
        super().__init__()
        self.session = session
        self.phase = "idle"
        self.problem_id: str | None = None
        self._answer_started = 0.0
        self._pending_quit = False
        self._pending_leave = False
        self._summary_open = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="session-shell"):
            yield Static("", id="session-stats")
            with Vertical(id="question-panel"):
                yield Static("", id="question")
                yield Input(placeholder="Type your answer and press Enter", id="answer")
                yield LoadingIndicator(id="judging")
                yield Static("", id="feedback")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#judging", LoadingIndicator).display = False
        self._advance()

    def _advance(self) -> None:
        self.problem_id = self.session.next_problem()
        self._pending_quit = False
        self._pending_leave = False

        question = self.query_one("#question", Static)
        answer = self.query_one("#answer", Input)
        feedback = self.query_one("#feedback", Static)
        judging = self.query_one("#judging", LoadingIndicator)

        feedback.update("")
        judging.display = False

        if self.problem_id is None:
            self.phase = "empty"
            question.update("This pack has no problems.")
            answer.disabled = True
            self._update_stats()
            return

        try:
            statement = self.session.render_statement(self.problem_id)
        except Exception as exc:  # noqa: BLE001
            self.phase = "error"
            question.update(Text(str(exc)))
            answer.disabled = True
            self.notify(str(exc), title="Unable to render problem", severity="error")
            return

        self.phase = "ready"
        self._answer_started = time.perf_counter()
        question.update(Text(statement))
        answer.value = ""
        answer.disabled = False
        answer.focus()
        self._update_stats()

    def _update_stats(self) -> None:
        stats = self.session.stats()
        self.query_one("#session-stats", Static).update(
            f"Mastered {stats.distinct_ac}/{stats.total_problems}  "
            f"Correct {stats.ac_count}/{stats.total_count}  "
            f"Combo {stats.combo}  "
            f"Avg {stats.avg_time:.2f}s"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.phase != "ready" or self.problem_id is None:
            return
        elapsed = self.session.elapsed(self._answer_started)
        self.phase = "judging"
        self.query_one("#answer", Input).disabled = True
        self.query_one("#judging", LoadingIndicator).display = True
        self.query_one("#feedback", Static).update("Judging...")
        self.run_worker(
            self._judge_answer(event.value, elapsed),
            name="judge",
            group="judge",
            exclusive=True,
        )

    async def _judge_answer(self, user_input: str, elapsed: float) -> None:
        assert self.problem_id is not None
        problem_id = self.problem_id

        while True:
            try:
                is_correct = await self.session.submit_answer(
                    problem_id,
                    user_input,
                    elapsed,
                )
                break
            except asyncio.CancelledError:
                self._resolve_pending_navigation()
                return
            except Exception as exc:  # noqa: BLE001
                action = await self.app.push_screen_wait(JudgeErrorDialog(exc))
                if action == "retry":
                    continue
                self.query_one("#judging", LoadingIndicator).display = False
                if action == "skip":
                    self.session.skip_problem(problem_id)
                    self._advance()
                    self._resolve_pending_navigation()
                    return
                await self._open_summary()
                return

        self.phase = "feedback"
        self.query_one("#judging", LoadingIndicator).display = False
        self._show_feedback(problem_id, is_correct, elapsed)
        self._update_stats()
        self._resolve_pending_navigation()

    def _show_feedback(
        self,
        problem_id: str,
        is_correct: bool,
        elapsed: float,
    ) -> None:
        feedback = self.query_one("#feedback", Static)
        if is_correct:
            expansion = self.session.expansion(problem_id)
            message = f"[green]Accepted[/green]  {elapsed:.2f}s"
            if expansion:
                message += f"\nExpansion: {escape(expansion)}"
        else:
            expected = self.session.expected_answer(problem_id)
            message = (
                "[red]Wrong answer[/red]\n"
                f"Expected: [yellow]{escape(expected)}[/yellow]"
            )
        feedback.update(message)

    def action_next_problem(self) -> None:
        if self.phase == "feedback":
            self._advance()

    def action_leave(self) -> None:
        if self.phase == "judging":
            self._pending_leave = True
            if self.session.async_judge:
                self._cancel_judge_workers()
            self.query_one("#feedback", Static).update(
                "Waiting for the current judgment to finish..."
            )
            return
        self.app.pop_screen()

    def request_quit(self) -> None:
        if self._summary_open:
            return
        if self.phase == "judging":
            self._pending_quit = True
            if self.session.async_judge:
                self._cancel_judge_workers()
            self.query_one("#feedback", Static).update(
                "Waiting for the current judgment to finish..."
            )
            return
        self.run_worker(
            self._open_summary(),
            name="summary",
            group="summary",
            exclusive=True,
        )

    def _cancel_judge_workers(self) -> None:
        for worker in self.workers:
            if worker.group == "judge":
                worker.cancel()

    def _resolve_pending_navigation(self) -> None:
        if self._pending_leave:
            self._pending_leave = False
            self.app.pop_screen()
        elif self._pending_quit:
            self._pending_quit = False
            self.run_worker(
                self._open_summary(),
                name="summary",
                group="summary",
                exclusive=True,
            )

    async def _open_summary(self) -> None:
        if self._summary_open:
            return
        self._summary_open = True
        try:
            should_end = await self.app.push_screen_wait(
                SessionSummaryDialog(self.session.stats())
            )
        finally:
            self._summary_open = False
        if should_end:
            self.app.exit()

    def on_unmount(self) -> None:
        self.session.close()
