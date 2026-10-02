"""Stable plugin-facing interfaces and lifecycle types."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .domain import ProblemMetadata

API_VERSION = "2"

type PluginResult = str | bool | None | Awaitable[str | bool | None]


def coerce_problem_metadata(value: object) -> ProblemMetadata:
    if value is None:
        return ProblemMetadata()
    if isinstance(value, ProblemMetadata):
        return value
    if isinstance(value, dict):
        tags = value.get("tags") or ()
        return ProblemMetadata(
            tags=tuple(str(tag) for tag in tags),
            difficulty=(
                float(value["difficulty"])
                if value.get("difficulty") is not None
                else None
            ),
            estimated_seconds=(
                float(value["estimated_seconds"])
                if value.get("estimated_seconds") is not None
                else None
            ),
            data=dict(value.get("data") or {}),
        )
    raise TypeError("Problem metadata must be ProblemMetadata, a mapping, or None")


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Host-owned paths supplied to a plugin during initialization."""

    pack_id: str
    pack_dir: Path
    workspace_dir: Path


@dataclass(frozen=True, slots=True)
class QuestionTypeDescriptor:
    """Stable metadata exposed by a plugin question type."""

    key: str
    label: str
    description: str = ""
    problem_count: int = 0


class QuestionType(Protocol):
    """The behavior owned by one selectable question type."""

    @property
    def key(self) -> str: ...

    @property
    def label(self) -> str: ...

    @property
    def description(self) -> str: ...

    def get_all_problem_ids(self) -> list[str] | Awaitable[list[str]]: ...

    def describe_problem(
        self,
        problem_id: str,
    ) -> (
        ProblemMetadata
        | dict[str, object]
        | None
        | Awaitable[ProblemMetadata | dict[str, object] | None]
    ): ...

    def render_statement(self, problem_id: str) -> PluginResult: ...

    def check_answer(
        self,
        problem_id: str,
        user_input: str,
    ) -> bool | Awaitable[bool]: ...

    def get_expected_display(self, problem_id: str) -> PluginResult: ...

    def get_expand_info(self, problem_id: str) -> PluginResult: ...


class Plugin(Protocol):
    """The complete host/plugin contract.

    Implementations may return either a value or an awaitable for each hook.
    The host adapter normalizes both forms.
    """

    def initialize(self, context: PluginContext) -> PluginResult: ...

    def get_question_types(
        self,
    ) -> list[QuestionType] | Awaitable[list[QuestionType]]: ...

    def close(self) -> None | Awaitable[None]: ...


class BaseTrainingPlugin:
    """Base class for Python training plugins."""

    def __init__(self, workspace_dir: str = "", pack_id: str | None = None):
        self.workspace_dir = workspace_dir
        self.pack_id = pack_id

    def initialize(self, context: PluginContext) -> None:
        self.workspace_dir = str(context.workspace_dir)
        self.pack_id = context.pack_id
        self.load_data()

    def load_data(self) -> None:
        """Load data from ``workspace_dir``; subclasses may override."""

    def get_question_types(self) -> list[QuestionType]:
        raise NotImplementedError

    def close(self) -> None:
        """Release plugin-owned resources."""
