"""Tests for src/core/helpers.py: Matchers, QuestionType, DataPlugin, FlashcardPlugin."""

import csv
import json
import os
from typing import ClassVar

import pytest

from src.core.helpers import (
    DataPlugin,
    FlashcardPlugin,
    Matchers,
    QuestionType,
)

# -----------------------------------------------------------------------
# Matchers
# -----------------------------------------------------------------------


class TestMatchersExact:
    def test_exact_match(self):
        m = Matchers.exact("name")
        assert m({"name": "hello"}, "hello")
        assert m({"name": "  hello  "}, "hello")

    def test_rejects_case_difference(self):
        m = Matchers.exact("name")
        assert not m({"name": "Hello"}, "hello")

    def test_rejects_wrong_value(self):
        m = Matchers.exact("name")
        assert not m({"name": "hello"}, "world")


class TestMatchersExactInteger:
    def test_strips_non_digits(self):
        m = Matchers.exact_integer("num")
        assert m({"num": 17}, "  17  ")
        assert m({"num": 17}, "#17")
        assert m({"num": 17}, "17abc")

    def test_rejects_wrong_digits(self):
        m = Matchers.exact_integer("num")
        assert not m({"num": 17}, "18")

    def test_empty_input(self):
        m = Matchers.exact_integer("num")
        assert not m({"num": 5}, "")


class TestMatchersCaseInsensitive:
    def test_ignores_case(self):
        m = Matchers.case_insensitive("sym")
        assert m({"sym": "He"}, "he")
        assert m({"sym": "He"}, "HE")
        assert m({"sym": "He"}, "  He  ")

    def test_rejects_wrong_value(self):
        m = Matchers.case_insensitive("sym")
        assert not m({"sym": "He"}, "H")


class TestMatchersChineseSymbolPair:
    def test_chinese_then_symbol(self):
        m = Matchers.chinese_symbol_pair("name", "sym")
        assert m({"name": "氢", "sym": "H"}, "氢H")

    def test_symbol_then_chinese(self):
        m = Matchers.chinese_symbol_pair("name", "sym")
        assert m({"name": "氢", "sym": "H"}, "H氢")

    def test_with_space(self):
        m = Matchers.chinese_symbol_pair("name", "sym")
        assert m({"name": "氢", "sym": "H"}, "氢 H")
        assert m({"name": "氢", "sym": "H"}, "H  氢")

    def test_rejects_wrong(self):
        m = Matchers.chinese_symbol_pair("name", "sym")
        assert not m({"name": "氢", "sym": "H"}, "氦H")
        assert not m({"name": "氢", "sym": "H"}, "氢He")


class TestMatchersAnyOrder:
    def test_space_separated(self):
        m = Matchers.any_order("period", "group")
        assert m({"period": 4, "group": "IVB"}, "4 IVB")

    def test_reversed_order(self):
        m = Matchers.any_order("period", "group")
        assert m({"period": 4, "group": "IVB"}, "IVB4")

    def test_no_separator(self):
        m = Matchers.any_order("period", "group")
        assert m({"period": 4, "group": "IVB"}, "4IVB")

    def test_rejects_partial(self):
        m = Matchers.any_order("period", "group")
        assert not m({"period": 4, "group": "IVB"}, "4")


class TestMatchersCustom:
    def test_delegates_to_function(self):
        def always_true(data_item, user_input):
            return True

        m = Matchers.custom(always_true)
        assert m({}, "anything")


# -----------------------------------------------------------------------
# QuestionType
# -----------------------------------------------------------------------


class TestQuestionType:
    def test_fields(self):
        stmt = lambda d: f"Q: {d['key']}"
        ans = lambda d: f"A: {d['key']}"
        matcher = Matchers.exact("key")

        qt = QuestionType(label="Test", statement=stmt, answer=ans, matcher=matcher)
        assert qt.label == "Test"
        assert qt.statement({"key": "v"}) == "Q: v"
        assert qt.answer({"key": "v"}) == "A: v"
        assert qt.matcher({"key": "v"}, "v")


# -----------------------------------------------------------------------
# DataPlugin
# -----------------------------------------------------------------------


class _SimpleDataPlugin(DataPlugin):
    """Minimal concrete DataPlugin for testing."""

    QUESTION_TYPES: ClassVar[list[QuestionType]] = [
        QuestionType(
            label="typeA",
            statement=lambda r: r["q"],
            answer=lambda r: r["a"],
            matcher=Matchers.exact("a"),
        ),
    ]

    def __init__(self, workspace_dir):
        super().__init__(workspace_dir)

    def load_records(self):
        return [
            {"q": "Q1", "a": "A1"},
            {"q": "Q2", "a": "A2"},
        ]


class _FilteredDataPlugin(DataPlugin):
    QUESTION_TYPES: ClassVar[list[QuestionType]] = [
        QuestionType(
            label="all",
            statement=lambda r: r["v"],
            answer=lambda r: r["v"],
            matcher=Matchers.exact("v"),
        ),
    ]

    def load_records(self):
        return [{"v": "a"}, {"v": "b"}, {"v": "c"}]

    def filter(self, record, q_type):
        return record["v"] != "b"


class TestDataPlugin:
    def test_get_all_problem_ids(self, tmp_workspace):
        p = _SimpleDataPlugin(tmp_workspace)
        ids = p.get_all_problem_ids()
        assert len(ids) == 2
        assert "0__typeA" in ids
        assert "1__typeA" in ids

    def test_render_statement(self, tmp_workspace):
        p = _SimpleDataPlugin(tmp_workspace)
        assert "Q1" in p.render_statement("0__typeA")
        assert "【typeA】" in p.render_statement("0__typeA")

    def test_check_answer_correct(self, tmp_workspace):
        p = _SimpleDataPlugin(tmp_workspace)
        assert p.check_answer("0__typeA", "A1")

    def test_check_answer_wrong(self, tmp_workspace):
        p = _SimpleDataPlugin(tmp_workspace)
        assert not p.check_answer("0__typeA", "wrong")

    def test_get_expected_display(self, tmp_workspace):
        p = _SimpleDataPlugin(tmp_workspace)
        assert p.get_expected_display("0__typeA") == "A1"

    def test_expand_info_default_empty(self, tmp_workspace):
        p = _SimpleDataPlugin(tmp_workspace)
        assert p.get_expand_info("0__typeA") == ""

    def test_resolve(self, tmp_workspace):
        p = _SimpleDataPlugin(tmp_workspace)
        record, qt = p._resolve("0__typeA")
        assert record == {"q": "Q1", "a": "A1"}
        assert qt.label == "typeA"

    def test_filter_excludes_records(self, tmp_workspace):
        p = _FilteredDataPlugin(tmp_workspace)
        ids = p.get_all_problem_ids()
        assert len(ids) == 2
        records = {p._resolve(pid)[0]["v"] for pid in ids}
        assert records == {"a", "c"}


# -----------------------------------------------------------------------
# FlashcardPlugin
# -----------------------------------------------------------------------


class _GreFlashcard(FlashcardPlugin):
    DATA_FILE = "words.csv"


class _JsonFlashcard(FlashcardPlugin):
    DATA_FILE = "words.json"


class TestFlashcardPlugin:
    def test_csv_loading(self, tmp_workspace):
        csv_path = os.path.join(tmp_workspace, "words.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["front", "back"])
            w.writerow(["apple", "苹果"])
            w.writerow(["dog", "狗"])

        p = _GreFlashcard(tmp_workspace)
        ids = p.get_all_problem_ids()
        assert len(ids) == 2
        assert p.render_statement("0") == "【闪卡】 apple"
        assert p.get_expected_display("0") == "苹果"
        assert p.check_answer("0", "苹果")

    def test_json_loading(self, tmp_workspace):
        json_path = os.path.join(tmp_workspace, "words.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {"front": "cat", "back": "猫"},
                    {"front": "bird", "back": "鸟"},
                ],
                f,
            )

        p = _JsonFlashcard(tmp_workspace)
        ids = p.get_all_problem_ids()
        assert len(ids) == 2
        assert p.render_statement("1") == "【闪卡】 bird"

    def test_rejects_wrong_answer(self, tmp_workspace):
        csv_path = os.path.join(tmp_workspace, "words.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["front", "back"])
            w.writerow(["hello", "world"])

        p = _GreFlashcard(tmp_workspace)
        assert not p.check_answer("0", "wrong")

    def test_unsupported_format_raises(self, tmp_workspace):
        class BadFlashcard(FlashcardPlugin):
            DATA_FILE = "data.txt"

        with open(os.path.join(tmp_workspace, "data.txt"), "w") as f:
            f.write("hello")

        with pytest.raises(ValueError, match="Unsupported DATA_FILE"):
            BadFlashcard(tmp_workspace)

    def test_missing_back_key_raises_keyerror(self, tmp_workspace):
        json_path = os.path.join(tmp_workspace, "words.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([{"front": "cat"}], f)  # Missing "back"

        p = _JsonFlashcard(tmp_workspace)
        # render_statement and get_expected_display use .get("back", ""), so they won't raise
        assert p.render_statement("0") == "【闪卡】 cat"
        assert p.get_expected_display("0") == ""

        # But check_answer uses Matchers.exact("back") which accesses data_item["back"] directly
        with pytest.raises(KeyError):
            p.check_answer("0", "anything")


class TestMatchersCornerCases:
    def test_missing_key_raises_keyerror(self):
        m1 = Matchers.exact("key")
        m2 = Matchers.exact_integer("key")
        m3 = Matchers.case_insensitive("key")
        m4 = Matchers.chinese_symbol_pair("key1", "key2")
        m5 = Matchers.any_order("key1", "key2")

        with pytest.raises(KeyError):
            m1({}, "val")
        with pytest.raises(KeyError):
            m2({}, "123")
        with pytest.raises(KeyError):
            m3({}, "val")
        with pytest.raises(KeyError):
            m4({"key1": "A"}, "val")  # Missing key2
        with pytest.raises(KeyError):
            m5({"key1": "A"}, "val")  # Missing key2
