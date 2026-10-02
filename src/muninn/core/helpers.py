"""Reusable helpers for data-driven training plugins."""

from __future__ import annotations

import csv
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from ..domain import ProblemMetadata
from ..plugin_api import (
    BaseTrainingPlugin,
    coerce_problem_metadata,
)


class Matchers:
    """Built-in matcher factories."""

    @staticmethod
    def exact(key: str):
        def match(data_item: dict, user_input: str) -> bool:
            return user_input.strip() == str(data_item[key]).strip()

        return match

    @staticmethod
    def exact_integer(key: str):
        def match(data_item: dict, user_input: str) -> bool:
            digits = re.sub(r"\D", "", user_input)
            return digits == str(data_item[key])

        return match

    @staticmethod
    def case_insensitive(key: str):
        def match(data_item: dict, user_input: str) -> bool:
            return user_input.strip().lower() == str(data_item[key]).strip().lower()

        return match

    @staticmethod
    def chinese_symbol_pair(key1: str, key2: str):
        def match(data_item: dict, user_input: str) -> bool:
            val1 = str(data_item[key1]).strip()
            val2 = str(data_item[key2]).strip()
            clean = re.sub(r"\s+", "", user_input).lower()
            return clean in ((val1 + val2).lower(), (val2 + val1).lower())

        return match

    @staticmethod
    def any_order(*keys: str):
        def match(data_item: dict, user_input: str) -> bool:
            clean_input = re.sub(r"[^a-zA-Z0-9]", "", user_input).upper()
            values = [
                re.sub(r"[^a-zA-Z0-9]", "", str(data_item[key])).upper() for key in keys
            ]
            return all(value in clean_input for value in values)

        return match

    @staticmethod
    def custom(fn: Callable[[dict, str], bool]):
        return fn


@dataclass(slots=True)
class QuestionTypeSpec:
    """Declarative definition used by :class:`DataPlugin`."""

    key: str
    label: str
    statement: Callable[[dict], str]
    answer: Callable[[dict], str]
    matcher: Callable[[dict, str], bool]
    description: str = ""
    expand: Callable[[dict], str] | None = None
    metadata: Callable[[dict], ProblemMetadata | dict[str, object] | None] | None = None

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("QuestionTypeSpec.key cannot be empty")
        if not self.label.strip():
            raise ValueError("QuestionTypeSpec.label cannot be empty")


class _DataQuestionType:
    def __init__(
        self,
        spec: QuestionTypeSpec,
        records: list[dict[str, Any]],
        record_id: Callable[[dict[str, Any], int], str],
        record_filter: Callable[[dict[str, Any], QuestionTypeSpec], bool],
    ) -> None:
        self.spec = spec
        self.key = spec.key
        self.label = spec.label
        self.description = spec.description
        self._problems: dict[str, dict[str, Any]] = {}
        for index, record in enumerate(records):
            if not record_filter(record, spec):
                continue
            problem_id = str(record_id(record, index))
            if problem_id in self._problems:
                raise ValueError(
                    f"Duplicate problem ID '{problem_id}' in question type '{self.key}'"
                )
            self._problems[problem_id] = record

    def get_all_problem_ids(self) -> list[str]:
        return list(self._problems)

    def describe_problem(self, problem_id: str) -> ProblemMetadata:
        record = self._problems[problem_id]
        if self.spec.metadata is None:
            return ProblemMetadata()
        return coerce_problem_metadata(self.spec.metadata(record))

    def render_statement(self, problem_id: str) -> str:
        return f"【{self.label}】 {self.spec.statement(self._problems[problem_id])}"

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        return self.spec.matcher(self._problems[problem_id], user_input.strip())

    def get_expected_display(self, problem_id: str) -> str:
        return self.spec.answer(self._problems[problem_id])

    def get_expand_info(self, problem_id: str) -> str:
        if self.spec.expand is None:
            return ""
        return self.spec.expand(self._problems[problem_id])


class DataPlugin(BaseTrainingPlugin):
    """Build multiple independently selectable question types from records."""

    QUESTION_TYPES: ClassVar[list[QuestionTypeSpec]] = []
    RECORD_ID_FIELD: ClassVar[str] = "id"

    def record_id(self, record: dict[str, Any], index: int) -> str:
        value = record.get(self.RECORD_ID_FIELD)
        if value is not None and str(value).strip():
            return str(value).strip()
        return f"legacy-{index}"

    def load_records(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def filter(self, record: dict, q_type: QuestionTypeSpec) -> bool:
        """Deprecated compatibility filter; prefer defining clean records."""

        del record, q_type
        return True

    def load_data(self) -> None:
        self._records = self.load_records()
        self._question_types = [
            _DataQuestionType(
                spec,
                self._records,
                self.record_id,
                self.filter,
            )
            for spec in self.QUESTION_TYPES
        ]

    def get_question_types(self):
        return list(self._question_types)


class FlashcardPlugin(DataPlugin):
    """Zero-boilerplate front/back flashcards."""

    DATA_FILE: str = ""
    EXPAND_FIELD: str | None = None
    RECORD_ID_FIELD: ClassVar[str] = "id"

    def record_id(self, record: dict[str, Any], index: int) -> str:
        for field in ("id", "front"):
            value = record.get(field)
            if value is not None and str(value).strip():
                return str(value).strip()
        return f"legacy-{index}"

    def load_records(self) -> list[dict[str, Any]]:
        path = os.path.join(self.workspace_dir, self.DATA_FILE)
        if path.endswith(".csv"):
            with open(path, encoding="utf-8", newline="") as file:
                return list(csv.DictReader(file))
        if path.endswith(".json"):
            with open(path, encoding="utf-8") as file:
                return json.load(file)
        raise ValueError(
            f"Unsupported DATA_FILE format: {self.DATA_FILE!r}. Expected .csv or .json"
        )

    def load_data(self) -> None:
        spec = QuestionTypeSpec(
            key="flashcard",
            label="闪卡",
            statement=lambda record: str(record.get("front", "")),
            answer=lambda record: str(record.get("back", "")),
            matcher=Matchers.exact("back"),
            expand=(
                (lambda record: str(record.get(self.EXPAND_FIELD or "", "")))
                if self.EXPAND_FIELD
                else None
            ),
        )
        self.QUESTION_TYPES = [spec]
        super().load_data()
