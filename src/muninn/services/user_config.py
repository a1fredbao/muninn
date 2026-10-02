"""Persistent user settings and training groups."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain import GroupSelection, PackKey, QuestionTypeKey, TrainingGroup

CONFIG_VERSION = 1
DEFAULT_THEME = "textual-dark"


class ConfigError(ValueError):
    """Raised when persisted user configuration is invalid."""


@dataclass(frozen=True, slots=True)
class UserConfig:
    theme: str = DEFAULT_THEME
    groups: tuple[TrainingGroup, ...] = ()


class UserConfigStore:
    """Read and atomically write ``~/.muninn/config.json``."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or os.path.expanduser("~/.muninn/config.json"))

    def load(self) -> UserConfig:
        if not self.path.exists():
            return UserConfig()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Unable to read configuration: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError("Configuration root must be a JSON object.")

        theme = str(raw.get("theme") or DEFAULT_THEME)
        groups_data = raw.get("groups") or []
        if not isinstance(groups_data, list):
            raise ConfigError("Configuration field 'groups' must be a list.")

        groups: list[TrainingGroup] = []
        for item in groups_data:
            groups.append(self._parse_group(item))
        return UserConfig(theme=theme, groups=tuple(groups))

    def save(self, config: UserConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CONFIG_VERSION,
            "theme": config.theme,
            "groups": [self._serialize_group(group) for group in config.groups],
        }
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".config-",
                suffix=".tmp",
                delete=False,
            ) as file:
                temp_path = file.name
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temp_path, self.path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def upsert_group(self, group: TrainingGroup) -> UserConfig:
        config = self.load()
        groups = [existing for existing in config.groups if existing.id != group.id]
        groups.append(group)
        updated = UserConfig(
            theme=config.theme,
            groups=tuple(sorted(groups, key=lambda item: item.name.casefold())),
        )
        self.save(updated)
        return updated

    def delete_group(self, group_id: str) -> UserConfig:
        config = self.load()
        updated = UserConfig(
            theme=config.theme,
            groups=tuple(group for group in config.groups if group.id != group_id),
        )
        self.save(updated)
        return updated

    def set_theme(self, theme: str) -> UserConfig:
        config = self.load()
        updated = UserConfig(theme=theme, groups=config.groups)
        self.save(updated)
        return updated

    @staticmethod
    def create_group(
        name: str,
        selections: list[GroupSelection],
        group_id: str | None = None,
    ) -> TrainingGroup:
        clean_name = name.strip()
        if not clean_name:
            raise ConfigError("Group name cannot be empty.")
        if len(clean_name) > 100:
            raise ConfigError("Group name cannot exceed 100 characters.")
        if any(character in clean_name for character in ("\x00", "\n", "\r")):
            raise ConfigError("Group name cannot contain control characters.")
        return TrainingGroup(
            id=group_id or uuid.uuid4().hex[:12],
            name=clean_name,
            selections=tuple(selections),
        )

    @staticmethod
    def _parse_group(value: Any) -> TrainingGroup:
        if not isinstance(value, dict):
            raise ConfigError("Each group must be a JSON object.")
        group_id = value.get("id")
        name = value.get("name")
        if not isinstance(group_id, str) or not group_id:
            raise ConfigError("Group field 'id' must be a non-empty string.")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("Group field 'name' must be a non-empty string.")

        selections_data = value.get("selections") or []
        if not isinstance(selections_data, list):
            raise ConfigError("Group field 'selections' must be a list.")
        selections: list[GroupSelection] = []
        for item in selections_data:
            if not isinstance(item, dict):
                raise ConfigError("Each group selection must be an object.")
            pack = item.get("pack")
            question_type = item.get("question_type")
            if not isinstance(pack, str) or not pack:
                raise ConfigError("Group selection requires a pack key.")
            if not isinstance(question_type, str) or not question_type:
                raise ConfigError("Group selection requires a question type key.")
            weight = float(item.get("weight", 1.0))
            if weight <= 0:
                raise ConfigError("Group selection weight must be positive.")
            selections.append(
                GroupSelection(
                    pack_key=PackKey(pack),
                    question_type_key=QuestionTypeKey(question_type),
                    weight=weight,
                    enabled=bool(item.get("enabled", True)),
                )
            )
        return TrainingGroup(
            id=group_id,
            name=name.strip(),
            selections=tuple(selections),
        )

    @staticmethod
    def _serialize_group(group: TrainingGroup) -> dict[str, Any]:
        return {
            "id": group.id,
            "name": group.name,
            "selections": [
                {
                    "pack": selection.pack_key,
                    "question_type": selection.question_type_key,
                    "weight": selection.weight,
                    "enabled": selection.enabled,
                }
                for selection in group.selections
            ],
        }
