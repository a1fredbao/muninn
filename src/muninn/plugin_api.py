"""Stable plugin-facing interfaces and lifecycle types."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

API_VERSION = "1"

type PluginResult = str | bool | None | Awaitable[str | bool | None]


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Host-owned paths supplied to a plugin during initialization."""

    pack_id: str
    pack_dir: Path
    workspace_dir: Path


class Plugin(Protocol):
    """The complete host/plugin contract.

    Implementations may return either a value or an awaitable for each hook.
    The host adapter normalizes both forms.
    """

    def initialize(self, context: PluginContext) -> PluginResult: ...

    def get_all_problem_ids(self) -> list[str] | Awaitable[list[str]]: ...

    def render_statement(self, problem_id: str) -> PluginResult: ...

    def check_answer(
        self,
        problem_id: str,
        user_input: str,
    ) -> bool | Awaitable[bool]: ...

    def get_expected_display(self, problem_id: str) -> PluginResult: ...

    def get_expand_info(self, problem_id: str) -> PluginResult: ...

    def close(self) -> None | Awaitable[None]: ...


class BaseTrainingPlugin:
    """Base class for Python training plugins."""

    def __init__(self, workspace_dir: str, pack_id: str | None = None):
        self.workspace_dir = workspace_dir
        self.pack_id = pack_id

    def initialize(self, context: PluginContext) -> None:
        self.workspace_dir = str(context.workspace_dir)
        self.pack_id = context.pack_id
        self.load_data()

    def load_data(self) -> None:
        """Load data from ``workspace_dir``; subclasses may override."""

    def get_all_problem_ids(self) -> list[str]:
        raise NotImplementedError

    def render_statement(self, problem_id: str) -> str:
        raise NotImplementedError

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        raise NotImplementedError

    def get_expected_display(self, problem_id: str) -> str:
        raise NotImplementedError

    def get_expand_info(self, problem_id: str) -> str:
        return ""

    def close(self) -> None:
        """Release plugin-owned resources."""
