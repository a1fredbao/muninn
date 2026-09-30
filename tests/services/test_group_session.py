"""Tests for cross-pack question-type composition."""

import asyncio
import json
from pathlib import Path

from muninn.domain import GroupSelection, PackKey, QuestionTypeKey, TrainingGroup
from muninn.keys import pack_key, question_type_key
from muninn.services.manifest import PackManifest
from muninn.services.package_manager import PackageManager
from muninn.services.session_factory import SessionFactory


def _write_group_pack(path: Path, pack_id: str) -> None:
    path.mkdir(parents=True)
    manifest = PackManifest(
        id=pack_id,
        name=pack_id,
        version="1.0.0",
        entrypoint="plugin:Plugin",
        api_version="2",
    )
    (path / "manifest.json").write_text(
        json.dumps(manifest.to_dict()),
        encoding="utf-8",
    )
    (path / "plugin.py").write_text(
        """from muninn.plugin_api import BaseTrainingPlugin


class FirstType:
    key = "first"
    label = "First"
    description = ""

    def get_all_problem_ids(self):
        return ["1", "2"]

    def describe_problem(self, problem_id):
        return {"tags": ["first"], "difficulty": 0.25}

    def render_statement(self, problem_id):
        return f"first:{problem_id}"

    def check_answer(self, problem_id, user_input):
        return user_input == problem_id

    def get_expected_display(self, problem_id):
        return problem_id

    def get_expand_info(self, problem_id):
        return ""


class SecondType(FirstType):
    key = "second"
    label = "Second"

    def get_all_problem_ids(self):
        return ["3"]

    def render_statement(self, problem_id):
        return f"second:{problem_id}"


class Plugin(BaseTrainingPlugin):
    def get_question_types(self):
        return [FirstType(), SecondType()]
""",
        encoding="utf-8",
    )


def test_group_mixes_selected_question_types_across_packs(tmp_path):
    packs_dir = tmp_path / "packs"
    manager = PackageManager(
        packs_dir=str(packs_dir),
        venvs_dir=str(tmp_path / "venvs"),
    )
    for pack_id in ("pack-a", "pack-b"):
        source = tmp_path / pack_id
        _write_group_pack(source, pack_id)
        manager.install_pack(str(source))

    factory = SessionFactory(
        manager,
        state_dir=str(tmp_path / "states"),
    )

    async def exercise():
        entries, errors = await factory.catalog.list_question_types()
        assert not errors
        selected = [
            entry
            for entry in entries
            if (
                (
                    entry.pack_id == "pack-a"
                    and entry.question_type_id in {"first", "second"}
                )
                or (entry.pack_id == "pack-b" and entry.question_type_id == "second")
            )
        ]
        group = TrainingGroup(
            id="group",
            name="Mixed",
            selections=tuple(
                GroupSelection(
                    pack_key=PackKey(pack_key(entry.pack_id)),
                    question_type_key=QuestionTypeKey(
                        question_type_key(entry.pack_id, entry.question_type_id)
                    ),
                )
                for entry in selected
            ),
        )

        session = await factory.create_group(group)
        try:
            assert session.stats().total_problems == 4
            rendered = {
                await session.render_statement(problem_id)
                for problem_id in session.problems
            }
            assert rendered == {"first:1", "first:2", "second:3"}
        finally:
            await session.aclose()

    asyncio.run(exercise())
