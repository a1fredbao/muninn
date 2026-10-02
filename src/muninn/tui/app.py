"""Textual application entry point."""

from __future__ import annotations

import asyncio
from typing import ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from ..services.package_manager import PackageManager
from ..services.session_factory import SessionFactory
from ..services.user_config import ConfigError, UserConfig, UserConfigStore
from .commands import MuninnCommandProvider
from .screens.group_builder import GroupBuilderScreen
from .screens.library import LibraryScreen
from .screens.session import SessionScreen


class MuninnApp(App[None]):
    """Muninn's Textual application."""

    CSS_PATH = "app.tcss"
    TITLE = "Muninn"
    SUB_TITLE = "An extensible training CLI"
    COMMANDS: ClassVar = App.COMMANDS | {MuninnCommandProvider}

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
        Binding("ctrl+t", "change_theme", "Theme", show=False),
    ]

    def __init__(
        self,
        initial_pack_id: str | None = None,
        package_manager: PackageManager | None = None,
        session_factory: SessionFactory | None = None,
        config_store: UserConfigStore | None = None,
        initial_group_id: str | None = None,
    ) -> None:
        super().__init__()
        self.package_manager = package_manager or PackageManager()
        self.session_factory = session_factory or SessionFactory(self.package_manager)
        self.config_store = config_store or UserConfigStore()
        self._config_error: str | None = None
        try:
            self.config = self.config_store.load()
        except ConfigError as exc:
            self.config = UserConfig()
            self._config_error = str(exc)
        self.initial_group_id = initial_group_id
        self.initial_pack_id = initial_pack_id
        self._library_screen: LibraryScreen | None = None
        self._catalog_entries = None
        self._catalog_errors: list[str] = []
        self._catalog_lock = asyncio.Lock()
        theme = self.config.theme
        if theme in self.available_themes:
            self.theme = theme

    def on_mount(self) -> None:
        self.theme_changed_signal.subscribe(self, self._persist_theme)
        if self._config_error:
            self.notify(
                self._config_error,
                title="Configuration reset",
                severity="warning",
            )
        if self.initial_group_id:
            self.push_screen(
                GroupBuilderScreen(
                    self.package_manager,
                    self.session_factory,
                    self.config_store,
                    initial_group_id=self.initial_group_id,
                    auto_start=True,
                )
            )
            return
        self._library_screen = LibraryScreen(
            self.package_manager,
            self.session_factory,
            self.config_store,
        )
        self.push_screen(self._library_screen)
        if self.initial_pack_id:
            self.call_after_refresh(self._open_initial_pack)

    def _open_initial_pack(self) -> None:
        if self._library_screen is not None and self.initial_pack_id:
            self._library_screen.open_pack(self.initial_pack_id)

    def _persist_theme(self, theme) -> None:
        try:
            self.config = self.config_store.set_theme(theme.name)
        except ConfigError as exc:
            self.notify(str(exc), title="Theme not saved", severity="error")

    async def get_catalog_entries(self, *, refresh: bool = False):
        async with self._catalog_lock:
            if self._catalog_entries is None or refresh:
                (
                    entries,
                    errors,
                ) = await self.session_factory.catalog.list_question_types()
                self._catalog_entries = entries
                self._catalog_errors = errors
            return list(self._catalog_entries), list(self._catalog_errors)

    def invalidate_catalog_cache(self) -> None:
        self._catalog_entries = None
        self._catalog_errors = []

    def run_group_from_palette(self, group_id: str) -> None:
        self.push_screen(
            GroupBuilderScreen(
                self.package_manager,
                self.session_factory,
                self.config_store,
                initial_group_id=group_id,
                auto_start=True,
            )
        )

    def open_question_type_from_palette(self, entry) -> None:
        for screen in reversed(self.screen_stack):
            if isinstance(screen, GroupBuilderScreen):
                screen.select_catalog_entry(entry)
                return
        self.push_screen(
            GroupBuilderScreen(
                self.package_manager,
                self.session_factory,
                self.config_store,
                initial_selection_keys={(entry.pack_key, entry.question_type_key)},
            )
        )

    def open_pack_from_palette(self, pack_id: str) -> None:
        library = LibraryScreen(
            self.package_manager,
            self.session_factory,
            self.config_store,
        )
        self.push_screen(library)
        self.call_after_refresh(library.open_pack, pack_id)

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
