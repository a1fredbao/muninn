# Muninn

Muninn (雾尼) - 高度可扩展的背诵/记忆命令行工具

## Muninn 是什么？

Muninn 是一个高度可扩展的命令行背诵软件，名字取自北欧神话中代表"记忆"的乌鸦雾尼。它不包含任何硬编码的题目，而是采用了**"宿主-插件 (Host-Plugin)" 架构**。你可以自由安装别人编写的"题库包"（比如化学元素表、GRE 单词、古诗文等），也可以自己使用 Python 轻松开发题库。

Muninn 作为"宿主"，为你提供了开箱即用的三大能力：

1. **智能出题调度算法**（根据历史正确率和耗时，专门盯着你的薄弱点出题）。
2. **状态与进度持久化**（你的每一次练习进度都会被保存下来，随时可以继续）。
3. 干净优雅的**终端 UI**。

## 安装与使用

我们推荐使用 `uv` 来全局安装 Muninn：

```bash
# 使用 uv 安装 (推荐)
uv tool install muninn

# 或者使用 pip 安装
pip install muninn
```

基础命令：

```bash
# 查看所有已安装的题库包
muninn list

# 安装一个外部题库包 (支持本地文件夹或 .zip 压缩包)
muninn install path/to/pack_or_zip

# 卸载一个已安装的题库包
muninn uninstall <pack_id>

# 运行指定的题库
muninn run <pack_id>

# 生成一个新的题库开发模板
muninn new <your_new_pack_id>
```

## 插件开发指南

Muninn 提供了分层 API，你可以根据需求选择最适合的层级。

### 快速上手：`FlashcardPlugin`（零样板代码）

对于纯正的"正面 → 背面"闪卡（比如背单词），只需准备一个 CSV 或 JSON 文件（包含 `front` / `back` 两列），然后写 3 行代码：

```python
from core.helpers import FlashcardPlugin


class Plugin(FlashcardPlugin):
    DATA_FILE = "words.csv"
```

即可。`FlashcardPlugin` 会自动处理题目渲染、答案判题和 ID 生成。

| 文件 | 说明 |
|------|------|
| `manifest.json` | 题库包的元数据（包名、作者、版本）。 |
| `words.csv` | 包含 `front` 和 `back` 两列的数据文件。 |
| `plugin.py` | 上面 3 行代码。 |

### 结构化数据：`DataPlugin` + `QuestionType`

当每条数据需要从多个角度出题时（"看元素背序号""看序号背元素""看位置背元素"……），使用 `DataPlugin`。你只需声明**题型列表**，Muninn 自动生成所有的题目组合。

**示例** — 化学元素从 4 个方向出题：

```python
import os, json
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
    ]

    def load_records(self) -> list:
        with open(
            os.path.join(self.workspace_dir, "elements.json"), encoding="utf-8"
        ) as f:
            return json.load(f)

    def filter(self, record, q_type):
        # 可选：过滤掉某些记录不参与某种题型
        return True
```

`DataPlugin` 自动生成题目 ID（格式 `{记录序号}__{题型标签}`）并路由全部五个接口方法。你只需提供数据 + 题型声明。

### 内置匹配器 (Matchers)

不必为每种题型手写正则，使用内置的 `Matchers` 工厂函数：

| 匹配器 | 说明 |
|--------|------|
| `Matchers.exact(key)` | 去除首尾空格后精确匹配。 |
| `Matchers.exact_integer(key)` | 提取输入中的数字后精确比较。 |
| `Matchers.case_insensitive(key)` | 忽略大小写匹配。 |
| `Matchers.chinese_symbol_pair(key1, key2)` | 匹配"中文+符号"或"符号+中文"任意顺序，忽略空格。 |
| `Matchers.any_order(*keys)` | 多个字段的值全部出现在输入中即判对，忽略分隔符和顺序。 |
| `Matchers.custom(fn)` | 传入自定义函数 `(record, user_input) -> bool`。 |

### 底层接口：`BaseRecitePlugin`

如果需要完全自定义，直接实现基础接口：

```python
from core.base_plugin import BaseRecitePlugin


class Plugin(BaseRecitePlugin):
    def load_data(self):
        # 从 self.workspace_dir 加载静态数据
        pass

    def get_all_problem_ids(self) -> list[str]:
        """返回所有题目的唯一 ID 列表。"""
        pass

    def render_statement(self, problem_id: str) -> str:
        """返回要在终端显示的问题文本。"""
        pass

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        """判断用户输入是否正确。"""
        pass

    def get_expected_display(self, problem_id: str) -> str:
        """答错时，返回给用户的标准答案。"""
        pass

    def get_expand_info(self, problem_id: str) -> str:
        """可选：答对时，返回拓展/提示信息。"""
        return ""
```

### 从零开始开发一个题库包

1. **生成开发模板**：

   ```bash
   muninn new my_cool_pack
   ```

   这会在当前目录下生成 `my_cool_pack/` 文件夹，包含 `manifest.json` 和骨架 `plugin.py`。

2. **编写逻辑**，选择上面三种方式之一。

3. **安装并测试**：

   ```bash
   muninn install ./my_cool_pack
   muninn run my_cool_pack
   ```
