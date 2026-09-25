"""Main pack library screen."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, LoadingIndicator, Static

from ...services.manifest import PackSummary
from ...services.package_manager import (
    CancellationToken,
    OperationCancelled,
    PackageManager,
    PackageProgress,
)
from ...services.session_factory import SessionFactory
from .dialogs import (
    ConfirmDialog,
    InstallDialog,
    OperationDialog,
)
from .session import SessionScreen


class LibraryScreen(Screen[None]):
    """List installed packs and expose all package-management actions."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "train", "Train", show=True, priority=True),
        Binding("i", "install", "Install", show=True),
        Binding("u", "upgrade_selected", "Upgrade", show=True),
        Binding("U", "upgrade_all", "Upgrade all", show=True),
        Binding("d", "uninstall", "Uninstall", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def __init__(
        self,
        package_manager: PackageManager,
        session_factory: SessionFactory,
    ) -> None:
        super().__init__()
        self.package_manager = package_manager
        self.session_factory = session_factory
        self._packs: dict[str, PackSummary] = {}
        self._loading_session = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="library-body"):
            yield DataTable(id="pack-table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="pack-details"):
                yield Static("Select a pack", id="pack-name")
                yield Static("", id="pack-metadata")
                yield Static("", id="pack-description")
                yield LoadingIndicator(id="session-loading")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#pack-table", DataTable)
        table.add_columns("ID", "Name", "Version", "Author")
        self.query_one("#session-loading", LoadingIndicator).display = False
        self.refresh_packs()
        table.focus()

    def refresh_packs(self) -> None:
        table = self.query_one("#pack-table", DataTable)
        table.clear()
        self._packs = {}

        for summary in self.package_manager.list_pack_summaries():
            pack_id = summary.pack_id
            self._packs[pack_id] = summary
            table.add_row(
                pack_id,
                summary.name,
                summary.version,
                summary.author,
                key=pack_id,
            )

        if self._packs:
            row = next(iter(self._packs))
            self._show_details(self._packs[row])
        else:
            self._clear_details()

    def _report_pack_progress(self, event: PackageProgress) -> None:
        self.notify(
            event.message,
            severity="warning",
            timeout=4,
            markup=False,
        )

    def _selected_pack_id(self) -> str | None:
        table = self.query_one("#pack-table", DataTable)
        if not table.rows:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return str(key.value) if key.value is not None else None

    def _show_details(self, pack: PackSummary) -> None:
        self.query_one("#pack-name", Static).update(pack.name)
        if not pack.valid:
            self.query_one("#pack-metadata", Static).update(
                f"ID: {pack.pack_id}\nStatus: invalid"
            )
            self.query_one("#pack-description", Static).update(
                pack.error or "The pack manifest is invalid."
            )
            return
        metadata = (
            f"ID: {pack.pack_id}\n"
            f"Version: {pack.version}\n"
            f"Author: {pack.author or '-'}\n"
            f"Source: {pack.source or '-'}"
        )
        self.query_one("#pack-metadata", Static).update(metadata)
        self.query_one("#pack-description", Static).update(pack.description)

    def _clear_details(self) -> None:
        self.query_one("#pack-name", Static).update("No packs installed")
        self.query_one("#pack-metadata", Static).update("Press i to install a pack.")
        self.query_one("#pack-description", Static).update("")

    def on_data_table_row_highlighted(
        self,
        event: DataTable.RowHighlighted,
    ) -> None:
        pack_id = event.row_key.value
        if pack_id is not None:
            self._show_details(self._packs[str(pack_id)])

    def on_data_table_row_selected(
        self,
        event: DataTable.RowSelected,
    ) -> None:
        self.action_train()

    def action_train(self) -> None:
        pack_id = self._selected_pack_id()
        if pack_id is not None:
            self.open_pack(pack_id)

    def open_pack(self, pack_id: str) -> None:
        if self._loading_session:
            return
        self._loading_session = True
        self.query_one("#session-loading", LoadingIndicator).display = True
        self.run_worker(
            self._load_session(pack_id),
            name=f"load-{pack_id}",
            group="session",
            exclusive=True,
        )

    async def _load_session(self, pack_id: str) -> None:
        try:
            session = await self.session_factory.create(pack_id)
        except Exception as exc:  # noqa: BLE001
            self.notify(str(exc), title="Unable to load pack", severity="error")
        else:
            await self.app.push_screen(SessionScreen(session))
        finally:
            self._loading_session = False
            self.query_one("#session-loading", LoadingIndicator).display = False

    def action_install(self) -> None:
        self.run_worker(
            self._install(),
            name="install-dialog",
            group="ui",
            exclusive=True,
        )

    async def _install(self) -> None:
        source = await self.app.push_screen_wait(InstallDialog())
        if not source:
            return

        def operation(progress, cancel_token):
            result = self.package_manager.install_pack_result(
                source,
                progress,
                cancel_token,
            )
            if not result.ok:
                return False, result.error or "Install failed."
            return True, f"Installed pack '{result.value}'."

        self._run_package_operation("Install pack", operation)

    async def action_upgrade_selected(self) -> None:
        pack_id = self._selected_pack_id()
        if pack_id is None:
            return

        def operation(progress, cancel_token):
            result = self.package_manager.upgrade_pack_result(
                pack_id,
                progress,
                cancel_token,
            )
            if result.failed:
                return False, result.error or f"Failed to upgrade '{pack_id}'."
            if result.upgraded:
                return True, (
                    f"Upgraded '{pack_id}' to version {result.remote_version}."
                )
            if result.status == "current":
                return True, f"Pack '{pack_id}' is already up to date."
            return True, result.error or f"Skipped '{pack_id}'."

        self._run_package_operation(f"Upgrade {pack_id}", operation)

    def action_upgrade_all(self) -> None:
        def operation(progress, cancel_token):
            results = self.package_manager.upgrade_all_results(
                progress,
                cancel_token,
            )
            failures = [result for result in results.values() if result.failed]
            if failures:
                return False, f"{len(failures)} pack(s) failed to upgrade."
            upgraded = sum(result.upgraded for result in results.values())
            return True, f"Upgrade complete; {upgraded} pack(s) upgraded."

        self._run_package_operation("Upgrade all packs", operation)

    def action_uninstall(self) -> None:
        self.run_worker(
            self._uninstall(),
            name="uninstall-dialog",
            group="ui",
            exclusive=True,
        )

    async def _uninstall(self) -> None:
        pack_id = self._selected_pack_id()
        if pack_id is None:
            return
        confirmed = await self.app.push_screen_wait(
            ConfirmDialog(
                "Uninstall pack",
                f"Remove '{pack_id}'? Training progress will be kept.",
            )
        )
        if not confirmed:
            return

        def operation(progress, cancel_token):
            result = self.package_manager.uninstall_pack_result(
                pack_id,
                progress,
                cancel_token,
            )
            if not result.ok:
                return False, result.error or f"Failed to uninstall '{pack_id}'."
            return True, f"Uninstalled pack '{pack_id}'."

        self._run_package_operation(f"Uninstall {pack_id}", operation)

    def action_refresh(self) -> None:
        self.refresh_packs()
        self.notify("Pack list refreshed.", timeout=2)

    def _run_package_operation(self, title: str, operation) -> None:
        cancel_token = CancellationToken()
        dialog = OperationDialog(title, cancel_token.cancel)
        self.app.push_screen(dialog)
        self.app.call_after_refresh(
            self._start_package_worker,
            dialog,
            operation,
            cancel_token,
        )

    def _start_package_worker(
        self,
        dialog: OperationDialog,
        operation,
        cancel_token: CancellationToken,
    ) -> None:
        self.run_worker(
            lambda: self._package_worker(dialog, operation, cancel_token),
            name="package-operation",
            group="package",
            exclusive=True,
            thread=True,
        )

    def _package_worker(
        self,
        dialog: OperationDialog,
        operation,
        cancel_token: CancellationToken,
    ) -> None:
        def progress(event: PackageProgress) -> None:
            self.app.call_from_thread(dialog.append, event.message)

        try:
            success, message = operation(progress, cancel_token)
        except OperationCancelled as exc:
            self.app.call_from_thread(dialog.finish, False, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(dialog.finish, False, str(exc))
        else:
            self.app.call_from_thread(dialog.finish, success, message)
        finally:
            self.app.call_from_thread(self.refresh_packs)
