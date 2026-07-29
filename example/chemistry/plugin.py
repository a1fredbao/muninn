import os
import json
import re
from core.base_plugin import BaseRecitePlugin


class Plugin(BaseRecitePlugin):
    def load_data(self):
        data_path = os.path.join(self.workspace_dir, "elements.json")
        with open(data_path, "r", encoding="utf-8") as f:
            self.elements = json.load(f)

        self.problems = {}
        for el in self.elements:
            num = el["num"]
            sym = el["sym"]
            name = el["name"]
            eng = el["eng"]
            period = el["period"]
            group = el["group"]

            # Type 1: 序号 -> 元素
            self.problems[f"1_{num}"] = {
                "type": 1,
                "element": el,
                "statement": f"【看序号背元素】 原子序数: {num}",
                "expected": f"{name} {sym}",
            }
            # Type 2: 元素 -> 序号
            self.problems[f"2_{num}"] = {
                "type": 2,
                "element": el,
                "statement": f"【看元素背序号】 元素: {name} ({sym})",
                "expected": str(num),
            }
            # Type 3 & 4 (skip group 0)
            if group != "0":
                self.problems[f"3_{num}"] = {
                    "type": 3,
                    "element": el,
                    "statement": f"【看位置背元素】 位置: 第{period}周期 {group}族",
                    "expected": f"{name} {sym}",
                }
                self.problems[f"4_{num}"] = {
                    "type": 4,
                    "element": el,
                    "statement": f"【看元素背位置】 元素: {name} ({sym})",
                    "expected": f"{period} {group}",
                }

    def get_all_problem_ids(self) -> list[str]:
        return list(self.problems.keys())

    def render_statement(self, problem_id: str) -> str:
        return self.problems[problem_id]["statement"]

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        p = self.problems[problem_id]
        q_type = p["type"]
        el = p["element"]

        if q_type in (1, 3):
            clean_in = re.sub(r"[^a-zA-Z\u4e00-\u9fa5]", "", user_input).lower()
            t1, t2 = (el["name"] + el["sym"]).lower(), (el["sym"] + el["name"]).lower()
            return clean_in in (t1, t2)

        elif q_type == 2:
            clean_in = re.sub(r"\D", "", user_input)
            return clean_in == str(el["num"])

        elif q_type == 4:
            clean_in = re.sub(r"[^0-9a-zA-Z]", "", user_input).upper()
            t1, t2 = (
                str(el["period"]) + el["group"].upper(),
                el["group"].upper() + str(el["period"]),
            )
            return clean_in in (t1, t2)

        return False

    def get_expected_display(self, problem_id: str) -> str:
        return self.problems[problem_id]["expected"]

    def get_expand_info(self, problem_id: str) -> str:
        el = self.problems[problem_id]["element"]
        return f"{el['eng']} ({el['sym']}, {el['name']}) - 第{el['period']}周期 {el['group']}族"
