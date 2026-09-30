"""Training group builder and launcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    LoadingIndicator,
    SelectionList,
    Static,
    Tree,
)

from ...domain import GroupSelection, PackKey, QuestionTypeKey, TrainingGroup
from ...services.catalog import QuestionTypeCatalogEntry
from ...services.package_manager import PackageManager
from ...services.session_factory import SessionFactory
from ...services.user_config import ConfigError, UserConfigStore
from .dialogs import ConfirmDialog
from .session import SessionScreen


@dataclass(frozen=True, slots=True)
class _PackNode:
    pack_key: str
    label: str


class GroupBuilderScreen(Screen[None]):
    """Select question types across packs and persist named groups."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "Back", show=True),
        Binding("n", "new_group", "New group", show=True),
        Binding("/", "search", "Search", show=False),
        Binding("ctrl+s", "save_group", "Save", show=True, priority=True),
        Binding("ctrl+r", "start_group", "Start", show=True, priority=True),
    ]

    def __init__(
        self,
        package_manager: PackageManager,
        session_factory: SessionFactory,
        config_store: UserConfigStore,
        *,
        initial_group_id: str | None = None,
        initial_selection_keys: set[tuple[str, str]] | None = None,
        auto_start: bool = False,
    ) -> None:
        super().__init__()
        self.package_manager = package_manager
        self.session_factory = session_factory
        self.config_store = config_store
        self.initial_group_id = initial_group_id
        self.initial_selection_keys = initial_selection_keys or set()
        self.auto_start = auto_start
        self._entries: list[QuestionTypeCatalogEntry] = []
        self._groups: list[TrainingGroup] = []
        self._selected_keys = set(self.initial_selection_keys)
        self._current_group_id: str | None = None
        self._updating_groups = False
        self._catalog_loaded = False
        self._auto_start_attempted = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="group-body"):
            with Vertical(id="group-sidebar"):
                yield Static("Training groups", classes="pane-title")
                yield SelectionList[str](id="group-list")
                with Vertical(classes="sidebar-actions"):
                    yield Button("New", id="new-group")
                    yield Button("Delete", id="delete-group", variant="error")
            with Vertical(id="group-catalog"):
                yield Static("Available question types", classes="pane-title")
                yield Tree[object]("Training catalog", id="catalog-tree")
            with Vertical(id="group-detail"):
                yield Static("Group details", classes="pane-title")
                yield Input(placeholder="Group name", id="group-name")
                yield Static("", id="group-summary")
                yield Static("", id="selection-summary")
                yield LoadingIndicator(id="group-loading")
                with Horizontal(classes="compact-actions"):
                    yield Button("Save", id="save-group", variant="primary")
                    yield Button("Start", id="start-group", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#group-loading", LoadingIndicator).display = False
        self._reload_groups()
        self.run_worker(
            self._load_catalog(),
            name="group-catalog",
            group="group-catalog",
            exclusive=True,
        )

    async def _load_catalog(self) -> None:
        loading = self.query_one("#group-loading", LoadingIndicator)
        loading.display = True
        try:
            loader = getattr(self.app, "get_catalog_entries", None)
            if loader is not None:
                entries, errors = await loader()
            else:
                (
                    entries,
                    errors,
                ) = await self.session_factory.catalog.list_question_types()
        except Exception as exc:  # noqa: BLE001
            self.notify(str(exc), title="Unable to load catalog", severity="error")
            return
        finally:
            loading.display = False

        self._entries = entries
        self._catalog_loaded = True
        self._rebuild_catalog_tree()
        if errors:
            self.notify(
                f"{len(errors)} pack(s) could not be loaded.",
                title="Catalog warnings",
                severity="warning",
            )
        if self.initial_group_id:
            self._select_group(self.initial_group_id)
            if self.auto_start and not self._auto_start_attempted:
                self._auto_start_attempted = True
                self.run_worker(
                    self._start_current_group(),
                    name="auto-start-group",
                    group="session",
                    exclusive=True,
                )

    def _reload_groups(self) -> None:
        try:
            self._groups = list(self.config_store.load().groups)
        except ConfigError as exc:
            self.notify(str(exc), title="Unable to load groups", severity="error")
            self._groups = []
        self._refresh_group_list()

    def _refresh_group_list(self) -> None:
        group_list = self.query_one("#group-list", SelectionList)
        self._updating_groups = True
        try:
            group_list.clear_options()
            for group in self._groups:
                group_list.add_option(
                    (
                        Text(group.name),
                        group.id,
                        group.id == self._current_group_id,
                    )
                )
        finally:
            self._updating_groups = False
        self._update_detail()

    def _rebuild_catalog_tree(self) -> None:
        tree = self.query_one("#catalog-tree", Tree)
        tree.clear()
        tree.root.expand()

        by_pack: dict[str, list[QuestionTypeCatalogEntry]] = {}
        for entry in self._entries:
            by_pack.setdefault(entry.pack_key, []).append(entry)

        for pack_key, entries in by_pack.items():
            pack_name = entries[0].pack_name
            pack_node = tree.root.add(
                Text(pack_name),
                data=_PackNode(pack_key=pack_key, label=pack_name),
                expand=True,
            )
            for entry in entries:
                checked = (
                    entry.pack_key,
                    entry.question_type_key,
                ) in self._selected_keys
                pack_node.add_leaf(
                    self._question_type_label(entry, checked),
                    data=entry,
                )

    @staticmethod
    def _question_type_label(
        entry: QuestionTypeCatalogEntry,
        checked: bool,
    ) -> Text:
        marker = "[x]" if checked else "[ ]"
        return Text(f"{marker} {entry.label} ({entry.problem_count})")

    def on_tree_node_selected(self, event: Tree.NodeSelected[object]) -> None:
        data = event.node.data
        if isinstance(data, QuestionTypeCatalogEntry):
            key = (data.pack_key, data.question_type_key)
            self._toggle_selection(key)
            event.node.set_label(
                self._question_type_label(
                    data,
                    key in self._selected_keys,
                )
            )
        elif isinstance(data, _PackNode):
            self._toggle_pack(data.pack_key)
            self._rebuild_catalog_tree()
        self._update_detail()

    def _toggle_selection(self, key: tuple[str, str]) -> None:
        if key in self._selected_keys:
            self._selected_keys.remove(key)
        else:
            self._selected_keys.add(key)

    def select_catalog_entry(self, entry: QuestionTypeCatalogEntry) -> None:
        key = (entry.pack_key, entry.question_type_key)
        self._selected_keys.add(key)
        self._rebuild_catalog_tree()
        self._update_detail()

    def _toggle_pack(self, pack_key: str) -> None:
        entries = [entry for entry in self._entries if entry.pack_key == pack_key]
        keys = {(entry.pack_key, entry.question_type_key) for entry in entries}
        if keys and keys <= self._selected_keys:
            self._selected_keys.difference_update(keys)
        else:
            self._selected_keys.update(keys)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "group-name":
            self._update_detail()

    def on_selection_list_selected_changed(
        self,
        event: SelectionList.SelectedChanged[str],
    ) -> None:
        if self._updating_groups or event.selection_list.id != "group-list":
            return
        group_ids = event.selection_list.selected
        if group_ids:
            selected = group_ids[-1]
            self._updating_groups = True
            try:
                for group_id in group_ids[:-1]:
                    event.selection_list.deselect(group_id)
            finally:
                self._updating_groups = False
            self._select_group(selected)

    def _select_group(self, group_id: str) -> None:
        group = next(
            (item for item in self._groups if item.id == group_id),
            None,
        )
        if group is None:
            return
        self._current_group_id = group.id
        self._selected_keys = {
            (selection.pack_key, selection.question_type_key)
            for selection in group.selections
            if selection.enabled
        }
        self.query_one("#group-name", Input).value = group.name
        self._rebuild_catalog_tree()
        self._refresh_group_list()

    def _draft_group(self) -> TrainingGroup:
        selections = [
            GroupSelection(
                pack_key=PackKey(pack_key),
                question_type_key=QuestionTypeKey(question_type_key),
            )
            for pack_key, question_type_key in sorted(self._selected_keys)
        ]
        return self.config_store.create_group(
            self.query_one("#group-name", Input).value,
            selections,
            group_id=self._current_group_id,
        )

    def _update_detail(self) -> None:
        selection_count = len(self._selected_keys)
        self.query_one("#group-summary", Static).update(
            Text(f"{selection_count} question type(s) selected")
        )
        lines: list[str] = []
        for entry in self._entries:
            key = (entry.pack_key, entry.question_type_key)
            if key in self._selected_keys:
                lines.append(f"{entry.pack_name} / {entry.label}")
        self.query_one("#selection-summary", Static).update(
            Text("\n".join(lines) if lines else "Select question types from the tree.")
        )

    def action_new_group(self) -> None:
        self._current_group_id = None
        self._selected_keys.clear()
        self.query_one("#group-name", Input).value = ""
        self._refresh_group_list()
        self._rebuild_catalog_tree()
        self._update_detail()

    def action_search(self) -> None:
        self.app.action_command_palette()

    def action_save_group(self) -> None:
        try:
            group = self._draft_group()
            self.config_store.upsert_group(group)
        except (ConfigError, ValueError) as exc:
            self.notify(str(exc), title="Unable to save group", severity="error")
            return
        self._current_group_id = group.id
        self._reload_groups()
        self.notify(f"Saved group '{group.name}'.", timeout=2)

    def action_start_group(self) -> None:
        self.run_worker(
            self._start_current_group(),
            name="start-group",
            group="session",
            exclusive=True,
        )

    async def _start_current_group(self) -> None:
        try:
            group = self._draft_group()
            if not group.selections:
                raise ValueError("Select at least one question type.")
            session = await self.session_factory.create_group(group)
        except (ConfigError, ValueError, RuntimeError) as exc:
            self.notify(str(exc), title="Unable to start group", severity="error")
            return
        await self.app.push_screen(SessionScreen(session))

    async def action_delete_group(self) -> None:
        if self._current_group_id is None:
            return
        group = next(
            (item for item in self._groups if item.id == self._current_group_id),
            None,
        )
        if group is None:
            return
        confirmed = await self.app.push_screen_wait(
            ConfirmDialog(
                "Delete training group",
                f"Delete '{group.name}'? Training progress will be kept.",
            )
        )
        if not confirmed:
            return
        self.config_store.delete_group(group.id)
        self.action_new_group()
        self._reload_groups()

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "new-group": self.action_new_group,
            "save-group": self.action_save_group,
            "start-group": self.action_start_group,
            "delete-group": self.action_delete_group,
        }
        action = actions.get(event.button.id or "")
        if action is not None:
            result = action()
            if result is not None:
                self.run_worker(result, group="group-action", exclusive=True)
