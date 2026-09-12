"""Modal dialogs used by the Textual application."""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RichLog, Static

from ...services.study_session import StudyStats


class ConfirmDialog(ModalScreen[bool]):
    """Ask for confirmation before a destructive action."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "cancel", "Cancel")]

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label(self.title, classes="dialog-title")
            yield Static(self.message)
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Confirm", id="confirm", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


class InstallDialog(ModalScreen[str | None]):
    """Collect a pack source from the user."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("Install pack", classes="dialog-title")
            yield Input(
                placeholder="Local path, zip, user/repo, or GitHub URL",
                id="install-source",
            )
            yield Static(
                "Examples: ./my-pack, user/repo@main, "
                "https://github.com/user/repo",
                classes="dialog-help",
            )
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Install", id="submit", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#install-source", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self._submit()
        else:
            self.dismiss(None)

    def _submit(self) -> None:
        value = self.query_one("#install-source", Input).value.strip()
        if value:
            self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class NewPackDialog(ModalScreen[tuple[str, str] | None]):
    """Collect the pack ID and target directory."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("Create plugin template", classes="dialog-title")
            yield Input(placeholder="Pack ID", id="new-pack-id")
            yield Input(value=".", placeholder="Target directory", id="new-pack-dir")
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Create", id="submit", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#new-pack-id", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "new-pack-dir":
            self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self._submit()
        else:
            self.dismiss(None)

    def _submit(self) -> None:
        pack_id = self.query_one("#new-pack-id", Input).value.strip()
        target_dir = self.query_one("#new-pack-dir", Input).value.strip() or "."
        if pack_id:
            self.dismiss((pack_id, target_dir))

    def action_cancel(self) -> None:
        self.dismiss(None)


class OperationDialog(ModalScreen[None]):
    """Display progress for one background package operation."""

    def __init__(
        self,
        title: str,
        cancel_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.cancel_callback = cancel_callback

    def compose(self) -> ComposeResult:
        with Container(classes="dialog operation-dialog"):
            yield Label(self.title, classes="dialog-title")
            yield Static("Starting...", id="operation-status")
            yield RichLog(id="operation-log", wrap=True, markup=False)
            with Horizontal(classes="dialog-actions"):
                yield Button(
                    "Cancel",
                    id="cancel",
                    disabled=self.cancel_callback is None,
                )
                yield Button("Close", id="close", disabled=True)

    def append(self, message: str) -> None:
        self.query_one("#operation-log", RichLog).write(message)

    def finish(self, success: bool, message: str) -> None:
        status = self.query_one("#operation-status", Static)
        status.update(message)
        status.set_class(not success, "error-text")
        status.set_class(success, "success-text")
        self.append(message)
        button = self.query_one("#close", Button)
        button.disabled = False
        self.query_one("#cancel", Button).disabled = True
        button.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(None)
        elif event.button.id == "cancel" and self.cancel_callback is not None:
            self.cancel_callback()
            event.button.disabled = True
            self.query_one("#operation-status", Static).update("Cancelling...")


class SessionSummaryDialog(ModalScreen[bool]):
    """Show the current session stats and offer continue or end."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "continue_session", "Continue")
    ]

    def __init__(self, stats: StudyStats) -> None:
        super().__init__()
        self.stats = stats

    def compose(self) -> ComposeResult:
        accuracy = f"{self.stats.accuracy * 100:.1f}%"
        with Container(classes="dialog"):
            yield Label("Session summary", classes="dialog-title")
            yield Static(
                f"Questions: {self.stats.total_count}\n"
                f"Correct: {self.stats.ac_count}\n"
                f"Accuracy: {accuracy}\n"
                f"Mastered: {self.stats.distinct_ac} / {self.stats.total_problems}\n"
                f"Best combo: {self.stats.combo}\n"
                f"Average correct time: {self.stats.avg_time:.2f}s"
            )
            with Horizontal(classes="dialog-actions"):
                yield Button("Continue", id="continue", variant="primary")
                yield Button("End session", id="end", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "end")

    def action_continue_session(self) -> None:
        self.dismiss(False)


class JudgeErrorDialog(ModalScreen[Literal["retry", "skip", "end"]]):
    """Recover from an exception raised by a plugin's judging hook."""

    BINDINGS: ClassVar[list[BindingType]] = [("escape", "end_session", "End")]

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("Judging failed", classes="dialog-title")
            yield Static(str(self.error), classes="error-text")
            with Horizontal(classes="dialog-actions"):
                yield Button("End session", id="end", variant="error")
                yield Button("Skip question", id="skip")
                yield Button("Retry", id="retry", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.id
        if action in {"retry", "skip", "end"}:
            self.dismiss(action)

    def action_end_session(self) -> None:
        self.dismiss("end")
