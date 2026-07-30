import csv
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from .base_plugin import BaseRecitePlugin

# ---------------------------------------------------------------------------
# Matchers – factory functions for reusable answer-checking logic
# ---------------------------------------------------------------------------


class Matchers:
    """Built-in matcher factories.

    Each classmethod returns a ``(data_item: dict, user_input: str) -> bool``
    callable, suitable for use as a ``QuestionType.matcher``.
    """

    @staticmethod
    def exact(key: str):
        """Exact match after stripping whitespace."""

        def match(data_item: dict, user_input: str) -> bool:
            return user_input.strip() == str(data_item[key]).strip()

        return match

    @staticmethod
    def exact_integer(key: str):
        """Extract digits from the user input and compare numerically."""

        def match(data_item: dict, user_input: str) -> bool:
            digits = re.sub(r"\D", "", user_input)
            return digits == str(data_item[key])

        return match

    @staticmethod
    def case_insensitive(key: str):
        """Case-insensitive match after stripping whitespace."""

        def match(data_item: dict, user_input: str) -> bool:
            return user_input.strip().lower() == str(data_item[key]).strip().lower()

        return match

    @staticmethod
    def chinese_symbol_pair(key1: str, key2: str):
        """Match "中文+符号" or "符号+中文" in either order, ignoring
        whitespace and case (for the Latin part)."""

        def match(data_item: dict, user_input: str) -> bool:
            val1 = str(data_item[key1]).strip()
            val2 = str(data_item[key2]).strip()
            clean = re.sub(r"\s+", "", user_input).lower()
            return clean in ((val1 + val2).lower(), (val2 + val1).lower())

        return match

    @staticmethod
    def any_order(*keys: str):
        """Match when all field values appear somewhere in the input,
        ignoring non-alphanumeric characters and case."""

        def match(data_item: dict, user_input: str) -> bool:
            clean_input = re.sub(r"[^a-zA-Z0-9]", "", user_input).upper()
            values = [
                re.sub(r"[^a-zA-Z0-9]", "", str(data_item[k])).upper() for k in keys
            ]
            return all(v in clean_input for v in values)

        return match

    @staticmethod
    def custom(fn: Callable[[dict, str], bool]):
        """Pass-through for a fully custom matcher function."""
        return fn


# ---------------------------------------------------------------------------
# QuestionType – a reusable question "direction"
# ---------------------------------------------------------------------------


@dataclass
class QuestionType:
    """Encapsulates one question direction: how to render the statement,
    how to render the expected answer, and how to check correctness."""

    label: str
    statement: Callable[[dict], str]
    answer: Callable[[dict], str]
    matcher: Callable[[dict, str], bool]


# ---------------------------------------------------------------------------
# DataPlugin – base class for record × QuestionType plugins
# ---------------------------------------------------------------------------


class DataPlugin(BaseRecitePlugin):
    """Higher-level plugin for "entity + multi-question-direction" scenarios.

    Subclasses supply:
    - ``QUESTION_TYPES``: a list of ``QuestionType`` instances.
    - ``load_records()``: returns a list of data dicts.
    - (optional) ``filter(record, q_type)``: return False to skip a
      particular record × question-type combination.

    ``DataPlugin`` auto-generates problem IDs, routes all five abstract
    methods, and exposes ``_resolve(problem_id) -> (record, q_type)`` for
    subclasses that need custom ``get_expand_info`` or similar overrides.
    """

    QUESTION_TYPES: ClassVar[list[QuestionType]] = []

    def load_data(self) -> None:
        self._records = self.load_records()
        self._problem_map: dict[str, tuple[dict, QuestionType]] = {}
        for i, record in enumerate(self._records):
            for qt in self.QUESTION_TYPES:
                if self.filter(record, qt):
                    pid = f"{i}__{qt.label}"
                    self._problem_map[pid] = (record, qt)

    def load_records(self) -> list[dict[str, Any]]:
        """Override to return a list of data records from workspace_dir."""
        raise NotImplementedError

    def filter(self, record: dict, q_type: QuestionType) -> bool:
        """Override to exclude some record × question-type combos."""
        return True

    def _resolve(self, problem_id: str) -> tuple[dict, QuestionType]:
        return self._problem_map[problem_id]

    # -- BaseRecitePlugin interface -----------------------------------------

    def get_all_problem_ids(self) -> list[str]:
        return list(self._problem_map.keys())

    def render_statement(self, problem_id: str) -> str:
        record, qt = self._resolve(problem_id)
        return f"【{qt.label}】 {qt.statement(record)}"

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        record, qt = self._resolve(problem_id)
        return qt.matcher(record, user_input.strip())

    def get_expected_display(self, problem_id: str) -> str:
        record, qt = self._resolve(problem_id)
        return qt.answer(record)

    def get_expand_info(self, problem_id: str) -> str:
        return ""


# ---------------------------------------------------------------------------
# FlashcardPlugin – zero-boilerplate front/back flashcard
# ---------------------------------------------------------------------------


class FlashcardPlugin(DataPlugin):
    """Plug-and-play flashcard-style plugin.

    Point ``DATA_FILE`` at a CSV (columns ``front``, ``back``) or JSON
    (list of ``{"front": ..., "back": ...}`` objects) in the workspace
    directory.  All five plugin methods are handled automatically.

    Example::

        class Plugin(FlashcardPlugin):
            DATA_FILE = "words.csv"
    """

    DATA_FILE: str = ""

    def load_data(self) -> None:
        path = os.path.join(self.workspace_dir, self.DATA_FILE)
        if path.endswith(".csv"):
            with open(path, encoding="utf-8", newline="") as f:
                self._records = list(csv.DictReader(f))
        elif path.endswith(".json"):
            with open(path, encoding="utf-8") as f:
                self._records = json.load(f)
        else:
            raise ValueError(
                f"Unsupported DATA_FILE format: {self.DATA_FILE!r}. "
                "Expected .csv or .json"
            )

        qt = QuestionType(
            label="闪卡",
            statement=lambda r: str(r.get("front", "")),
            answer=lambda r: str(r.get("back", "")),
            matcher=Matchers.exact("back"),
        )

        self._problem_map: dict[str, tuple[dict, QuestionType]] = {}
        for i, record in enumerate(self._records):
            self._problem_map[str(i)] = (record, qt)
