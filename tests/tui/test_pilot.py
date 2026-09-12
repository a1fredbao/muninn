"""Textual Pilot coverage for the main screens."""

import asyncio
import time
from unittest.mock import MagicMock

from textual.widgets import DataTable

from src.core.base_plugin import BaseRecitePlugin
from src.services.package_manager import PackageProgress
from src.services.study_session import StudySession
from src.tui.app import MuninnApp
from src.tui.screens.dialogs import (
    InstallDialog,
    OperationDialog,
    SessionSummaryDialog,
)
from src.tui.screens.session import SessionScreen


class _PackageManager:
    def __init__(self):
        self.installed = []

    def list_packs(self):
        return [
            {
                "id": "sample",
                "name": "Sample Pack",
                "version": "2.1.0",
                "author": "Tester",
                "description": "Metadata visible in the library.",
                "source": "local:/tmp/sample",
            }
        ]

    def install_pack(self, source, progress=None, cancel_token=None):
        self.installed.append(source)
        if progress:
            progress(PackageProgress("Installed for test"))
        return "installed"


class _SlowPlugin(BaseRecitePlugin):
    def __init__(self):
        super().__init__("")

    def load_data(self):
        self.ids = ["1"]

    def get_all_problem_ids(self):
        return self.ids

    def render_statement(self, problem_id):
        return "Slow question"

    def check_answer(self, problem_id, user_input):
        time.sleep(0.25)
        return user_input == problem_id

    def get_expected_display(self, problem_id):
        return "1"


def _state_manager() -> MagicMock:
    state = MagicMock()
    state.get_stats.return_value = {
        "ac_count": 0,
        "total_count": 0,
        "total_ac_time": 0.0,
    }
    return state


def test_library_screen_shows_pack_metadata():
    async def exercise():
        app = MuninnApp(package_manager=_PackageManager())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            table = app.screen.query_one("#pack-table", DataTable)
            metadata = app.screen.query_one("#pack-metadata")
            assert len(table.rows) == 1
            assert "2.1.0" in str(metadata.render())
            assert "local:/tmp/sample" in str(metadata.render())

    asyncio.run(exercise())


def test_library_exposes_management_dialog_and_quit_binding():
    async def exercise():
        manager = _PackageManager()
        app = MuninnApp(package_manager=manager)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            assert any(
                binding.binding.key == "ctrl+q"
                for binding in app.screen.active_bindings.values()
            )
            await pilot.press("i")
            await pilot.pause()
            assert isinstance(app.screen, InstallDialog)
            app.screen.query_one("#install-source").value = "source-path"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause(0.05)
                if manager.installed:
                    break
            assert manager.installed == ["source-path"]
            assert isinstance(app.screen, OperationDialog)

    asyncio.run(exercise())


def test_slow_sync_judging_does_not_block_pilot():
    async def exercise():
        session = StudySession("slow", _SlowPlugin(), _state_manager())
        app = MuninnApp(package_manager=_PackageManager())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await app.push_screen(SessionScreen(session))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SessionScreen)

            await pilot.click("#answer")
            await pilot.press("1", "enter")
            ticks = 0
            while screen.phase == "judging":
                await asyncio.sleep(0.01)
                ticks += 1

            assert ticks >= 5
            assert screen.phase == "feedback"
            assert session.stats().total_count == 1
            await pilot.press("ctrl+q")
            await pilot.pause()
            assert isinstance(app.screen, SessionSummaryDialog)

    asyncio.run(exercise())
