# Muninn

Muninn (雾尼) - An Extensible Reciting CLI.

[中文文档](./README_zh.md)

## What is Muninn?

Muninn is a highly extensible CLI application designed to help you memorize anything. Instead of hardcoding questions, Muninn relies on a **Plugin Architecture**. You can install "Reciting Packs" created by others (like chemistry elements, GRE vocabulary, or historical events) or develop your own packs using Python.

Muninn acts as a "host" that provides:

1. A **Smart Scheduling Algorithm** (focuses on your weak-points).
2. **Persistent State Management** (remembers your progress across sessions).
3. A clean, distraction-free **Terminal UI**.

## Installation & Usage

Install Muninn globally using `uv` (recommended) or `pip`:

```bash
# Using uv (Recommended)
uv tool install muninn

# Or using pip
pip install muninn
```

Available commands:

```bash
# List all installed packs
muninn list

# Install a pack (supports directories or .zip files)
muninn install path/to/pack_or_zip

# Uninstall a previously installed pack
muninn uninstall <pack_id>

# Run a specific pack by ID
muninn run <pack_id>

# Generate a new plugin template for development
muninn new <your_new_pack_id>
```

## Plugin Development Guide

Muninn provides a layered API. Choose the level that fits your needs.

### Quickstart: `FlashcardPlugin` (zero boilerplate)

For simple front/back flashcards (e.g. GRE words), create a CSV or JSON file with `front` and `back` columns, then write a 3-line plugin:

```python
from core.helpers import FlashcardPlugin


class Plugin(FlashcardPlugin):
    DATA_FILE = "words.csv"
```

That's it. `FlashcardPlugin` handles rendering, answer-checking, and ID generation automatically.

| File | Description |
|------|-------------|
| `manifest.json` | Pack metadata (name, author, version). |
| `words.csv` | Data with `front` and `back` columns. |
| `plugin.py` | The 3-line plugin above. |

### For structured data: `DataPlugin` + `QuestionType`

When each data record can be quizzed from multiple angles, use `DataPlugin`. Declare your **question types** and let Muninn generate all problem variants automatically.

**Example** — Chemistry elements quizzed from 4 directions (symbol → name, name → number, etc.):

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
        # Optional: skip certain question types for specific records
        return True
```

`DataPlugin` auto-generates problem IDs (`{record_index}__{question_label}`) and routes all five interface methods. You only supply data + question types.

### Built-in Matchers

Instead of writing custom regex for every question type, use the built-in `Matchers` factories:

| Matcher | Behavior |
|---------|----------|
| `Matchers.exact(key)` | Exact match after trimming whitespace. |
| `Matchers.exact_integer(key)` | Extract digits, compare numerically. |
| `Matchers.case_insensitive(key)` | Case-insensitive match. |
| `Matchers.chinese_symbol_pair(key1, key2)` | Match "中文+符号" or "符号+中文" in any order. |
| `Matchers.any_order(*keys)` | Match all field values appearing anywhere in the input. |
| `Matchers.custom(fn)` | Pass your own `(record, user_input) -> bool` function. |

### Low-level: `BaseRecitePlugin`

For full control, implement the base interface directly:

```python
from core.base_plugin import BaseRecitePlugin


class Plugin(BaseRecitePlugin):
    def load_data(self):
        # Load static data from self.workspace_dir
        pass

    def get_all_problem_ids(self) -> list[str]:
        """Return all unique problem IDs."""
        pass

    def render_statement(self, problem_id: str) -> str:
        """Return the question text to display."""
        pass

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        """Return True if correct."""
        pass

    def get_expected_display(self, problem_id: str) -> str:
        """Return the correct answer to show on failure."""
        pass

    def get_expand_info(self, problem_id: str) -> str:
        """Optional: Return extra info to show on success."""
        return ""
```

### Developing a pack from scratch

1. **Generate a template**:

   ```bash
   muninn new my_cool_pack
   ```

   This creates a `my_cool_pack/` directory with `manifest.json` and a skeleton `plugin.py`.

2. **Write your logic** using one of the approaches above.

3. **Install and test**:

   ```bash
   muninn install ./my_cool_pack
   muninn run my_cool_pack
   ```
