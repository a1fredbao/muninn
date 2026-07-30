# Muninn API 扩展规划 - 面向插件开发者的辅助层

## 背景：当前问题

以 `example/chemistry/plugin.py` 为例，开发者目前需要：

1. 手动维护一个 `self.problems` 字典，每个 "方向" 都需要完整填写 `type`, `element`, `statement`, `expected` 字段
2. 在 `check_answer` 中用 `if q_type == ...` 分支处理不同题型的判题逻辑
3. 自己实现所有容错匹配（忽略大小写、空格、输入顺序等）
4. 即使是最简单的正反面闪卡，也要实现全部 5 个抽象方法

---

## 目标：降低插件开发者的心智负担

Muninn 的 `src/core/` 层新增一组 **辅助工具 (Helpers)**，让开发者专注于"数据"和"语义"，而不是"胶水代码"。

---

## 1. `QuestionType` —— 可复用的题型单元

### 设计思路

把"一种问答方向"抽象成一个独立的 `QuestionType` 对象。它封装了三件事：

- 如何**渲染**题目（给定数据项，生成题目文本）
- 如何**渲染**预期答案（给定数据项，生成标准答案文本）
- 如何**判断**用户输入是否正确（使用内置的 Matcher，详见第 2 节）

```python
# 插件开发者的代码
from core.helpers import QuestionType, Matchers

# 把一种"问答方向"声明为一行
q_num_to_element = QuestionType(
    label="看序号背元素",
    statement=lambda el: f"原子序数: {el['num']}",
    answer=lambda el: f"{el['name']} {el['sym']}",
    matcher=Matchers.chinese_symbol_pair("name", "sym"),  # 内置容错匹配
)
```

### 注册到插件

```python
class Plugin(BaseRecitePlugin):
    QUESTION_TYPES = [
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
    ]
```

---

## 2. `Matchers` —— 内置容错匹配器

常见的输入容错逻辑不应该由每个插件重复实现。Muninn 提供一组开箱即用的 Matcher 工厂函数：

| Matcher                                    | 说明                                             | 示例                      |
| ------------------------------------------ | ------------------------------------------------ | ------------------------- |
| `Matchers.exact(key)`                      | 精确匹配某字段（去除首尾空格）                   | 完全相同的字符串          |
| `Matchers.exact_integer(key)`              | 只提取数字后精确匹配                             | `" 17 "` / `"#17"` → `17` |
| `Matchers.case_insensitive(key)`           | 忽略大小写匹配                                   | 英文单词背诵              |
| `Matchers.chinese_symbol_pair(key1, key2)` | 匹配"中文+符号"或"符号+中文"任意顺序，忽略空格   | `氢H` / `H氢` / `氢 H`    |
| `Matchers.any_order(*keys)`                | 多个字段任意顺序输入，忽略分隔符                 | 周期+族 `4 IVB` / `IVB4`  |
| `Matchers.custom(fn)`                      | 传入自定义函数 `(data_item, user_input) -> bool` | 完全自由扩展              |

---

## 3. `DataPlugin` —— 面向"实体+多题型"场景的高阶基类

### 设计思路

当一组 `QuestionType` 需要应用到一批数据上（"每条数据 × 每种题型 = 一道题"），这个模式极其常见。`DataPlugin` 是 `BaseRecitePlugin` 的子类，它自动完成 ID 生成、问题注册和方法路由，开发者只需提供：

1. 数据加载逻辑 `load_records()` → 返回记录列表
2. 题型列表 `QUESTION_TYPES`
3. 可选的过滤器 `filter(record, q_type)` → 某条数据是否参与某种题型

### 改写后的 chemistry plugin（从 87 行缩减到 ~40 行）

```python
import os
import json
from core.helpers import DataPlugin, QuestionType, Matchers


class Plugin(DataPlugin):
    QUESTION_TYPES = [
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
        """过滤掉 0 族元素的位置类题目"""
        if q_type.label in ("看位置背元素", "看元素背位置"):
            return record["group"] != "0"
        return True

    def get_expand_info(self, problem_id: str) -> str:
        el, _ = self._resolve(problem_id)
        return f"{el['eng']} ({el['sym']}, {el['name']}) - 第{el['period']}周期 {el['group']}族"
```

---

## 4. `FlashcardPlugin` —— 最简单的闪卡场景

对于纯粹的"正面→背面"记忆（如 GRE 单词、古诗词），提供一个更高阶的 `FlashcardPlugin`，实现 0 样板代码的目标：

```python
# flashcard 格式 CSV / JSON：每条数据有 front, back 两个字段即可
class Plugin(FlashcardPlugin):
    DATA_FILE = "words.csv"

    # FlashcardPlugin 自动实现 load_records, get_all_problem_ids,
    # render_statement, check_answer, get_expected_display
    # 开发者完全不需要写任何一行额外代码（除非需要定制）
```

---

## 5. 实现计划

### Phase 1：`Matchers` + `QuestionType`

- 在 `src/core/helpers.py` 中实现 `Matchers` 工具类和 `QuestionType` 数据类
- 无需修改 `BaseRecitePlugin`，完全向后兼容

### Phase 2：`DataPlugin`

- 在 `src/core/helpers.py` 中实现 `DataPlugin(BaseRecitePlugin)` 子类
- 将 `example/chemistry/plugin.py` 改写为 `DataPlugin` 版本作为验证

### Phase 3：`FlashcardPlugin`

- 支持从 CSV/JSON 自动加载 `front/back` 格式数据
- 提供一个示例闪卡包（如 GRE 单词）验证

---

## 附：改动涉及文件

```text
src/
└── core/
    ├── base_plugin.py    # 不变
    ├── helpers.py        # ✅ 新增：QuestionType, Matchers, DataPlugin, FlashcardPlugin
    ├── scheduler.py      # 不变
    └── state.py          # 不变

example/
├── chemistry/plugin.py   # ✅ 改写为 DataPlugin 版本（用于验证）
└── flashcard/            # ✅ 新增：FlashcardPlugin 示例包
```
