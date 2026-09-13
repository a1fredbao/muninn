"""Textual application entry point."""

from __future__ import annotations

from typing import ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from ..services.package_manager import PackageManager
from .screens.library import LibraryScreen
from .screens.session import SessionScreen


class MuninnApp(App[None]):
    """Muninn's Textual application."""

    CSS_PATH = "app.tcss"
    TITLE = "Muninn"
    SUB_TITLE = "Extensible Reciting"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "ctrl+c",
            "request_quit",
            "Quit",
            show=True,
            priority=True,
        ),
        Binding(
            "ctrl+q",
            "show_quit_notice",
            "Quit",
            show=False,
            priority=True,
        ),
    ]

    def __init__(
        self,
        initial_pack_id: str | None = None,
        package_manager: PackageManager | None = None,
    ) -> None:
        super().__init__()
        self.package_manager = package_manager or PackageManager()
        self.initial_pack_id = initial_pack_id
        self._library_screen: LibraryScreen | None = None

    def on_mount(self) -> None:
        self._library_screen = LibraryScreen(self.package_manager)
        self.push_screen(self._library_screen)
        if self.initial_pack_id:
            self.call_after_refresh(self._open_initial_pack)

    def _open_initial_pack(self) -> None:
        if self._library_screen is not None and self.initial_pack_id:
            self._library_screen.open_pack(self.initial_pack_id)

    def action_request_quit(self) -> None:
        for screen in reversed(self.screen_stack):
            if isinstance(screen, SessionScreen):
                screen.request_quit()
                return
        self.exit()

    def action_show_quit_notice(self) -> None:
        self.notify(
            "Press Ctrl+C to quit.",
            title="Use Ctrl+C",
            severity="warning",
        )
