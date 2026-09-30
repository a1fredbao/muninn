"""Textual coverage for the training group builder."""

import asyncio

from textual.widgets import Input, Tree

from muninn.keys import pack_key, question_type_key
from muninn.services.catalog import QuestionTypeCatalogEntry
from muninn.services.package_manager import PackageManager
from muninn.services.session_factory import SessionFactory
from muninn.services.user_config import UserConfigStore
from muninn.tui.app import MuninnApp
from muninn.tui.commands import MuninnCommandProvider
from muninn.tui.screens.group_builder import GroupBuilderScreen


class _Catalog:
    def __init__(self):
        self.entries = [
            QuestionTypeCatalogEntry(
                pack_id="chemistry",
                pack_name="Chemistry",
                pack_key=pack_key("chemistry"),
                question_type_id="number-to-element",
                question_type_key=question_type_key(
                    "chemistry",
                    "number-to-element",
                ),
                label="Number to element",
                description="",
                problem_count=36,
            ),
            QuestionTypeCatalogEntry(
                pack_id="japanese",
                pack_name="Japanese",
                pack_key=pack_key("japanese"),
                question_type_id="kana-to-romaji",
                question_type_key=question_type_key(
                    "japanese",
                    "kana-to-romaji",
                ),
                label="Kana to romaji",
                description="",
                problem_count=46,
            ),
        ]

    async def list_question_types(self):
        return list(self.entries), []


class _SessionFactory:
    def __init__(self):
        self.catalog = _Catalog()

    async def create_group(self, group):
        raise AssertionError(f"Unexpected session start: {group}")


def test_group_builder_selects_searches_and_saves_question_types(tmp_path):
    async def exercise():
        config_store = UserConfigStore(str(tmp_path / "config.json"))
        package_manager = PackageManager(
            packs_dir=str(tmp_path / "packs"),
            venvs_dir=str(tmp_path / "venvs"),
        )
        app = MuninnApp(
            package_manager=package_manager,
            session_factory=_SessionFactory(),
            config_store=config_store,
        )
        async with app.run_test(size=(120, 36)) as pilot:
            screen = GroupBuilderScreen(
                package_manager=package_manager,
                session_factory=app.session_factory,
                config_store=config_store,
            )
            await app.push_screen(screen)
            for _ in range(50):
                await pilot.pause(0.01)
                if screen._catalog_loaded:
                    break

            tree = screen.query_one("#catalog-tree", Tree)
            chemistry = tree.root.children[0]
            first_type = chemistry.children[0]
            screen.on_tree_node_selected(Tree.NodeSelected(first_type))
            assert len(screen._selected_keys) == 1

            provider = MuninnCommandProvider(app.screen)
            await provider.startup()
            hits = [hit async for hit in provider.search("japanese")]
            assert hits

            screen.query_one("#group-name", Input).value = "Mixed training"
            screen.action_save_group()
            saved = config_store.load().groups
            assert len(saved) == 1
            assert saved[0].name == "Mixed training"
            assert len(saved[0].selections) == 1

    asyncio.run(exercise())


def test_theme_change_is_persisted(tmp_path):
    async def exercise():
        config_store = UserConfigStore(str(tmp_path / "config.json"))
        app = MuninnApp(
            package_manager=PackageManager(
                packs_dir=str(tmp_path / "packs"),
                venvs_dir=str(tmp_path / "venvs"),
            ),
            session_factory=SessionFactory(
                PackageManager(
                    packs_dir=str(tmp_path / "packs"),
                    venvs_dir=str(tmp_path / "venvs"),
                )
            ),
            config_store=config_store,
        )
        async with app.run_test(size=(100, 30)) as pilot:
            app.theme = "nord"
            await pilot.pause()

        assert config_store.load().theme == "nord"

    asyncio.run(exercise())
