"""Textual Pilot coverage for the main screens."""

import asyncio
import time
from pathlib import Path

from textual.containers import Container
from textual.widgets import DataTable, TextArea

from muninn.core.state import StateManager
from muninn.plugin_api import BaseTrainingPlugin
from muninn.services.manifest import PackManifest, PackSummary
from muninn.services.operations import OperationResult
from muninn.services.package_manager import PackageProgress
from muninn.services.plugin_loader import (
    InProcessPluginAdapter,
    LoadedPlugin,
)
from muninn.services.training_session import TrainingSession
from muninn.tui.app import MuninnApp
from muninn.tui.screens.dialogs import (
    InstallDialog,
    JudgeErrorDialog,
    OperationDialog,
    SessionSummaryDialog,
)
from muninn.tui.screens.session import SessionScreen


class _PackageManager:
    def __init__(self):
        self.installed = []

    def list_pack_summaries(self):
        return [
            PackSummary(
                "sample",
                PackManifest(
                    id="sample",
                    name="Sample Pack",
                    version="2.1.0",
                    author="Tester",
                    description="Metadata visible in the library.",
                    source="local:/tmp/sample",
                ),
            )
        ]

    def install_pack(self, source, progress=None, cancel_token=None):
        self.installed.append(source)
        if progress:
            progress(PackageProgress("Installed for test"))
        return "installed"

    def install_pack_result(self, source, progress=None, cancel_token=None):
        return OperationResult.success(
            self.install_pack(source, progress, cancel_token)
        )

    def uninstall_pack_result(
        self,
        pack_id,
        progress=None,
        cancel_token=None,
    ):
        return OperationResult.success(pack_id)


class _SlowPlugin(BaseTrainingPlugin):
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


class _CapturePlugin(BaseTrainingPlugin):
    def __init__(self):
        self.received = []
        super().__init__("")

    def load_data(self):
        self.ids = ["1"]

    def get_all_problem_ids(self):
        return self.ids

    def render_statement(self, problem_id):
        return "Multiline question"

    def check_answer(self, problem_id, user_input):
        self.received.append(user_input)
        return True

    def get_expected_display(self, problem_id):
        return "1"


class _FailingPlugin(BaseTrainingPlugin):
    def __init__(self):
        super().__init__("")

    def load_data(self):
        self.ids = ["1"]

    def get_all_problem_ids(self):
        return self.ids

    def render_statement(self, problem_id):
        return "Failing question"

    def check_answer(self, problem_id, user_input):
        raise RuntimeError("judge failed")

    def get_expected_display(self, problem_id):
        return "1"


class _RenderFailingPlugin(_FailingPlugin):
    def render_statement(self, problem_id):
        raise RuntimeError("render failed")


async def _make_session(plugin: BaseTrainingPlugin, tmp_path: Path, pack_id: str):
    pack_dir = tmp_path / pack_id
    pack_dir.mkdir()
    loaded = LoadedPlugin(
        pack_id=pack_id,
        pack_dir=pack_dir,
        manifest=PackManifest(
            id=pack_id,
            name=pack_id,
            version="1.0.0",
            entrypoint="plugin:Plugin",
            api_version="1",
        ),
        entrypoint="plugin:Plugin",
        environment={},
    )
    adapter = InProcessPluginAdapter(loaded, plugin)
    store = StateManager(pack_id, str(tmp_path / "states"))
    return await TrainingSession.create(pack_id, adapter, store)


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
            assert app.screen.active_bindings["ctrl+c"].binding.show
            assert not app.screen.active_bindings["ctrl+q"].binding.show
            assert (
                app.screen.active_bindings["ctrl+q"].binding.action
                == "show_quit_notice"
            )
            assert "ctrl+p" in app.screen.active_bindings
            assert "n" not in app.screen.active_bindings
            await pilot.press("i")
            await pilot.pause()
            assert isinstance(app.screen, InstallDialog)
            dialog_region = app.screen.query_one(".dialog", Container).region
            assert dialog_region.x == (app.screen.size.width - dialog_region.width) // 2
            assert (
                dialog_region.y == (app.screen.size.height - dialog_region.height) // 2
            )
            app.screen.query_one("#install-source").value = "source-path"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause(0.05)
                if manager.installed:
                    break
            assert manager.installed == ["source-path"]
            assert isinstance(app.screen, OperationDialog)

    asyncio.run(exercise())


def test_ctrl_c_quits_library_immediately():
    async def exercise():
        app = MuninnApp(package_manager=_PackageManager())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert not app.is_running

    asyncio.run(exercise())


def test_ctrl_p_opens_command_palette():
    async def exercise():
        app = MuninnApp(package_manager=_PackageManager())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert type(app.screen).__name__ == "CommandPalette"

    asyncio.run(exercise())


def test_ctrl_q_shows_notice_without_quitting():
    async def exercise():
        app = MuninnApp(package_manager=_PackageManager())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+q")
            await pilot.pause()
            assert app.is_running
            assert any(
                "Ctrl+C" in notification.message for notification in app._notifications
            )

    asyncio.run(exercise())


def test_slow_sync_judging_does_not_block_pilot(tmp_path):
    async def exercise():
        session = await _make_session(_SlowPlugin(), tmp_path, "slow")
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
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert isinstance(app.screen, SessionSummaryDialog)

    asyncio.run(exercise())


def test_multiline_answer_submits_on_enter(tmp_path):
    async def exercise():
        plugin = _CapturePlugin()
        session = await _make_session(plugin, tmp_path, "multiline")
        app = MuninnApp(package_manager=_PackageManager())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await app.push_screen(SessionScreen(session))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SessionScreen)
            answer = screen.query_one("#answer", TextArea)
            initial_height = answer.region.height

            await pilot.click("#answer")
            await pilot.press("a", "ctrl+enter", "b", "super+enter", "c")
            await pilot.pause()
            assert answer.text == "a\nb\nc"
            assert answer.region.height > initial_height

            await pilot.press("enter")
            while screen.phase == "judging":
                await asyncio.sleep(0.01)

            assert screen.phase == "feedback"
            assert plugin.received == ["a\nb\nc"]

    asyncio.run(exercise())


def test_continue_from_judge_error_restores_answer_input(tmp_path):
    async def exercise():
        session = await _make_session(_FailingPlugin(), tmp_path, "failing")
        app = MuninnApp(package_manager=_PackageManager())
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await app.push_screen(SessionScreen(session))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SessionScreen)

            await pilot.click("#answer")
            await pilot.press("1", "enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if isinstance(app.screen, JudgeErrorDialog):
                    break
            assert isinstance(app.screen, JudgeErrorDialog)

            await pilot.click("#end")
            await pilot.pause()
            assert isinstance(app.screen, SessionSummaryDialog)
            await pilot.press("escape")
            await pilot.pause()

            assert app.screen is screen
            assert screen.phase == "ready"
            assert not screen.query_one("#answer", TextArea).disabled

    asyncio.run(exercise())


def test_render_error_can_skip_problem(tmp_path):
    async def exercise():
        session = await _make_session(
            _RenderFailingPlugin(),
            tmp_path,
            "render-failing",
        )
        app = MuninnApp(package_manager=_PackageManager())
        async with app.run_test(size=(100, 30)) as pilot:
            await app.push_screen(SessionScreen(session))
            for _ in range(50):
                await pilot.pause(0.02)
                if isinstance(app.screen, JudgeErrorDialog):
                    break

            assert isinstance(app.screen, JudgeErrorDialog)
            await pilot.click("#skip")
            await pilot.pause()

            assert isinstance(app.screen, SessionScreen)
            assert app.screen.phase == "empty"

    asyncio.run(exercise())
