import json
import os
from typing import ClassVar

from core.helpers import DataPlugin, Matchers, QuestionType


class Plugin(DataPlugin):
    QUESTION_TYPES: ClassVar[list[QuestionType]] = [
        QuestionType(
            label="看序号背元素",
            statement=lambda el: f"原子序数: {el['num']}",
            answer=lambda el: f"{el['name']} {el['sym']}",
            matcher=Matchers.chinese_symbol_pair("name", "sym"),
        ),
        QuestionType(
            label="看元素背序号",
            statement=lambda el: f"元素: {el['name']} ({el['sym']})",
            answer=lambda el: str(el["num"]),
            matcher=Matchers.exact_integer("num"),
        ),
        QuestionType(
            label="看位置背元素",
            statement=lambda el: f"位置: 第{el['period']}周期 {el['group']}族",
            answer=lambda el: f"{el['name']} {el['sym']}",
            matcher=Matchers.chinese_symbol_pair("name", "sym"),
        ),
        QuestionType(
            label="看元素背位置",
            statement=lambda el: f"元素: {el['name']} ({el['sym']})",
            answer=lambda el: f"{el['period']} {el['group']}",
            matcher=Matchers.any_order("period", "group"),
        ),
    ]

    def load_records(self) -> list:
        with open(
            os.path.join(self.workspace_dir, "elements.json"), encoding="utf-8"
        ) as f:
            return json.load(f)

    def filter(self, record: dict, q_type: QuestionType) -> bool:
        # 排除 0 族元素的位置类题目.
        if record["group"] == "0":
            return q_type.label not in ("看位置背元素", "看元素背位置")

        # 排除 VIII 族元素的看位置背元素题目
        if record["group"] == "VIII":
            return q_type.label != "看位置背元素"
        return True

    def get_expand_info(self, problem_id: str) -> str:
        el, _ = self._resolve(problem_id)
        return (
            f"{el['eng']} ({el['sym']}, {el['name']})"
            f" - 第{el['period']}周期 {el['group']}族"
        )
