"""Tests for persistent groups and theme settings."""

import json

import pytest

from muninn.domain import GroupSelection, PackKey, QuestionTypeKey
from muninn.services.user_config import ConfigError, UserConfigStore


def test_persists_theme_and_multiple_groups(tmp_path):
    store = UserConfigStore(str(tmp_path / "config.json"))
    first = store.create_group(
        "Chemistry basics",
        [
            GroupSelection(
                pack_key=PackKey("pack_hash"),
                question_type_key=QuestionTypeKey("type_hash"),
            )
        ],
    )
    second = store.create_group("Mixed training", [])

    store.upsert_group(first)
    store.upsert_group(second)
    store.set_theme("nord")

    loaded = store.load()
    assert loaded.theme == "nord"
    assert {group.name for group in loaded.groups} == {
        "Chemistry basics",
        "Mixed training",
    }


def test_delete_group(tmp_path):
    store = UserConfigStore(str(tmp_path / "config.json"))
    group = store.create_group("Temporary", [])
    store.upsert_group(group)

    updated = store.delete_group(group.id)

    assert updated.groups == ()


def test_rejects_invalid_group_selection(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "groups": [
                    {
                        "id": "group",
                        "name": "Group",
                        "selections": [
                            {
                                "pack": "",
                                "question_type": "type",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        UserConfigStore(str(path)).load()
