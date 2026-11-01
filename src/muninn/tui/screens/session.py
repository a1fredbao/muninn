"""Interactive training session screen."""

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
from textual.widgets import Footer, Header, LoadingIndicator, Static, TextArea

from ...domain import AttemptOutcome
from ...services.training_session import (
    AnswerAcceptanceRequired,
    TrainingSession,
)
from .dialogs import (
    JudgeErrorDialog,
    SessionSummaryDialog,
)


class SessionScreen(Screen[None]):
    """Ask questions while keeping the Textual event loop responsive."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "leave", "Library", show=True),
        Binding("enter", "submit_answer", "Submit", show=True, priority=True),
        Binding("y", "accept_answer", "Accept", show=False),
        Binding("n", "reject_answer", "Reject", show=False),
        Binding(
            "ctrl+enter",
            "insert_newline",
            "New line",
            show=False,
            priority=True,
        ),
        Binding(
            "super+enter",
            "insert_newline",
            "New line",
            show=False,
            priority=True,
        ),
    ]

    def __init__(self, session: TrainingSession) -> None:
        super().__init__()
        self.session = session
        self.phase = "idle"
        self.problem_id: str | None = None
        self._answer_started = 0.0
        self._pending_quit = False
        self._pending_leave = False
        self._summary_open = False
        self._confirmation: tuple[str, str, float] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="session-shell"):
            yield Static("", id="session-stats")
            with Vertical(id="question-panel"):
                yield Static("", id="question")
                yield TextArea(
                    placeholder="Enter submits; Ctrl+Enter adds a new line",
                    id="answer",
                    soft_wrap=True,
                )
                yield LoadingIndicator(id="judging")
                yield Static("", id="feedback")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#judging", LoadingIndicator).display = False
        self._start_advance()

    def _start_advance(self) -> None:
        self.run_worker(
            self._advance(),
            name="advance",
            group="advance",
            exclusive=True,
        )

    async def _advance(self) -> None:
        self.problem_id = self.session.next_problem()
        self._pending_quit = False
        self._pending_leave = False
        self._confirmation = None

        question = self.query_one("#question", Static)
        answer = self.query_one("#answer", TextArea)
        feedback = self.query_one("#feedback", Static)
        judging = self.query_one("#judging", LoadingIndicator)

        feedback.update("")
        judging.display = False

        statement: str | None = None
        while self.problem_id is not None and statement is None:
            try:
                statement = await self.session.render_statement(self.problem_id)
            except Exception as exc:  # noqa: BLE001
                action = await self.app.push_screen_wait(JudgeErrorDialog(exc))
                if action == "retry":
                    continue
                if action == "skip":
                    self.session.skip_problem(self.problem_id)
                    self.problem_id = self.session.next_problem()
                    continue
                should_end = await self._open_summary()
                if should_end:
                    return

        if self.problem_id is None or statement is None:
            self.phase = "empty"
            question.update("This pack has no problems.")
            answer.disabled = True
            self._update_stats()
            return

        self.phase = "ready"
        self._answer_started = time.perf_counter()
        question.update(Text(statement))
        answer.text = ""
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

    def action_submit_answer(self) -> None:
        if self.phase == "feedback":
            self._start_advance()
            return
        if self.phase != "ready" or self.problem_id is None:
            return
        answer = self.query_one("#answer", TextArea)
        user_input = answer.text
        elapsed = self.session.elapsed(self._answer_started)
        self.phase = "judging"
        answer.disabled = True
        self.query_one("#judging", LoadingIndicator).display = True
        self.query_one("#feedback", Static).update("Judging...")
        self.run_worker(
            self._judge_answer(user_input, elapsed),
            name="judge",
            group="judge",
            exclusive=True,
        )

    def action_insert_newline(self) -> None:
        if self.phase == "ready":
            self.query_one("#answer", TextArea).insert("\n")

    async def _judge_answer(self, user_input: str, elapsed: float) -> None:
        assert self.problem_id is not None
        problem_id = self.problem_id

        while True:
            try:
                try:
                    result = await self.session.submit_answer_result(
                        problem_id,
                        user_input,
                        elapsed,
                    )
                except AnswerAcceptanceRequired as exc:
                    if self._pending_quit or self._pending_leave:
                        self._resolve_pending_navigation()
                        return
                    expected = await self.session.expected_answer(exc.problem_id)
                    self._confirmation = (exc.problem_id, exc.user_input, elapsed)
                    self.phase = "confirming"
                    answer = self.query_one("#answer", TextArea)
                    answer.disabled = True
                    self.set_focus(None)
                    self.query_one("#judging", LoadingIndicator).display = False
                    self.query_one("#feedback", Static).update(
                        "[red]Wrong answer[/red]\n"
                        f"Expected: [yellow]{escape(expected)}[/yellow]\n\n"
                        "[grey]Is this an acceptable answer? (y/n)[/grey]"
                    )
                    return
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
                    await self._advance()
                    self._resolve_pending_navigation()
                    return
                should_end = await self._open_summary()
                if not should_end:
                    self._restore_current_problem()
                return

        self.phase = "feedback"
        self._confirmation = None
        self.query_one("#judging", LoadingIndicator).display = False
        await self._show_feedback(problem_id, result.outcome, elapsed)
        self._update_stats()
        self._resolve_pending_navigation()

    def action_accept_answer(self) -> None:
        self._start_confirmation(True)

    def action_reject_answer(self) -> None:
        self._start_confirmation(False)

    def _start_confirmation(self, accepted: bool) -> None:
        if self.phase != "confirming" or self._confirmation is None:
            return
        self.phase = "judging"
        self.query_one("#judging", LoadingIndicator).display = True
        self.query_one("#feedback", Static).update("Saving...")
        self.run_worker(
            self._record_confirmation(accepted),
            name="judge",
            group="judge",
            exclusive=True,
        )

    async def _record_confirmation(self, accepted: bool) -> None:
        assert self._confirmation is not None
        problem_id, user_input, elapsed = self._confirmation

        while True:
            try:
                result = self.session.submit_answer_confirmation(
                    problem_id,
                    user_input,
                    elapsed,
                    accepted,
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
                    self._confirmation = None
                    await self._advance()
                    self._resolve_pending_navigation()
                    return
                should_end = await self._open_summary()
                if not should_end:
                    self._restore_current_problem()
                return

        self._confirmation = None
        self.phase = "feedback"
        self.query_one("#judging", LoadingIndicator).display = False
        await self._show_feedback(problem_id, result.outcome, elapsed)
        self._update_stats()
        self._resolve_pending_navigation()

    async def _show_feedback(
        self,
        problem_id: str,
        outcome: AttemptOutcome,
        elapsed: float,
    ) -> None:
        feedback = self.query_one("#feedback", Static)
        if outcome.is_correct:
            expansion = await self.session.expansion(problem_id)
            label = "Accepted (confirmed)" if outcome.user_confirmed else "Accepted"
            message = f"[green]{label}[/green]  {elapsed:.2f}s"
            if expansion:
                message += f"\nExpansion: {escape(expansion)}"
        else:
            expected = await self.session.expected_answer(problem_id)
            message = (
                "[red]Wrong answer[/red]\n"
                f"Expected: [yellow]{escape(expected)}[/yellow]"
            )
            if outcome.user_confirmed:
                message += "\nYou marked this answer as unacceptable."
        feedback.update(message)

    def _restore_current_problem(self) -> None:
        """Make the current problem answerable again after a recoverable error."""

        self._confirmation = None
        self.phase = "ready"
        self._answer_started = time.perf_counter()
        self.query_one("#judging", LoadingIndicator).display = False
        self.query_one("#feedback", Static).update("")
        answer = self.query_one("#answer", TextArea)
        answer.disabled = False
        answer.focus()
        self._update_stats()

    def action_leave(self) -> None:
        if self.phase == "judging":
            self._pending_leave = True
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

    async def _open_summary(self) -> bool:
        if self._summary_open:
            return False
        self._summary_open = True
        try:
            should_end = await self.app.push_screen_wait(
                SessionSummaryDialog(self.session.stats())
            )
        finally:
            self._summary_open = False
        if should_end:
            self.app.exit()
        return should_end

    def on_unmount(self) -> None:
        asyncio.create_task(self.session.aclose())
