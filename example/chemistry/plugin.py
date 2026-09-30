import json
import os
from typing import ClassVar

from muninn.core.helpers import DataPlugin, Matchers, QuestionTypeSpec


def _expand(element: dict) -> str:
    return (
        f"{element['eng']} ({element['sym']}, {element['name']})"
        f" - 第{element['period']}周期 {element['group']}族"
    )


def _metadata(element: dict) -> dict:
    return {
        "tags": ["chemistry", "periodic-table"],
        "data": {"atomic_number": element["num"]},
    }


class Plugin(DataPlugin):
    QUESTION_TYPES: ClassVar[list[QuestionTypeSpec]] = [
        QuestionTypeSpec(
            key="number-to-element",
            label="看序号练元素",
            statement=lambda el: f"原子序数: {el['num']}",
            answer=lambda el: f"{el['name']} {el['sym']}",
            matcher=Matchers.chinese_symbol_pair("name", "sym"),
            expand=_expand,
            metadata=_metadata,
        ),
        QuestionTypeSpec(
            key="element-to-number",
            label="看元素练序号",
            statement=lambda el: f"元素: {el['name']} ({el['sym']})",
            answer=lambda el: str(el["num"]),
            matcher=Matchers.exact_integer("num"),
            expand=_expand,
            metadata=_metadata,
        ),
        QuestionTypeSpec(
            key="position-to-element",
            label="看位置练元素",
            statement=lambda el: f"位置: 第{el['period']}周期 {el['group']}族",
            answer=lambda el: f"{el['name']} {el['sym']}",
            matcher=Matchers.chinese_symbol_pair("name", "sym"),
            expand=_expand,
            metadata=_metadata,
        ),
        QuestionTypeSpec(
            key="element-to-position",
            label="看元素练位置",
            statement=lambda el: f"元素: {el['name']} ({el['sym']})",
            answer=lambda el: f"{el['period']} {el['group']}",
            matcher=Matchers.any_order("period", "group"),
            expand=_expand,
            metadata=_metadata,
        ),
    ]

    def record_id(self, record: dict, index: int) -> str:
        del index
        return str(record["num"])

    def load_records(self) -> list:
        with open(
            os.path.join(self.workspace_dir, "elements.json"), encoding="utf-8"
        ) as f:
            return json.load(f)

    def filter(self, record: dict, q_type: QuestionTypeSpec) -> bool:
        # 排除 0 族元素的位置类题目.
        if record["group"] == "0":
            return q_type.key not in ("position-to-element", "element-to-position")

        # 排除 VIII 族元素的位置类题目。
        if record["group"] == "VIII":
            return q_type.key != "position-to-element"
        return True
