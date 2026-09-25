# DataPlugin

`DataPlugin` is a higher-level wrapper around `BaseTrainingPlugin` designed
for the common pattern "a set of records multiplied by a set of question
directions". Declare your question types and Muninn generates all problem
variants automatically.

## Quick Example

```python
import json
import os
from typing import ClassVar

from muninn.core.helpers import DataPlugin, Matchers, QuestionType


class Plugin(DataPlugin):
    QUESTION_TYPES: ClassVar[list[QuestionType]] = [
        QuestionType(
            key="symbol-to-name",
            label="Symbol -> Name",
            statement=lambda el: f"Element: {el['sym']}",
            answer=lambda el: el["name"],
            matcher=Matchers.case_insensitive("name"),
        ),
        QuestionType(
            key="name-to-number",
            label="Name -> Number",
            statement=lambda el: f"Element: {el['name']}",
            answer=lambda el: str(el["num"]),
            matcher=Matchers.exact_integer("num"),
        ),
    ]

    def load_records(self) -> list:
        path = os.path.join(self.workspace_dir, "elements.json")
        with open(path, encoding="utf-8") as file:
            return json.load(file)
```

## QUESTION_TYPES

`QUESTION_TYPES` is a list of `QuestionType` objects. Each represents one
question direction.

Use a stable `key` for persistence. The human-readable `label` may change
without invalidating progress.

## load_records()

Override `load_records()` to return a list of dictionaries from the
workspace. Include a stable `id` field in each record.

If the record uses another primary key, override `record_id()`:

```python
def record_id(self, record: dict, index: int) -> str:
    del index
    return str(record["num"])
```

## filter(record, q_type)

Optional. Return `False` to skip one record and question-direction
combination.

```python
def filter(self, record, q_type):
    if q_type.key == "position-to-element":
        return record["group"] != "0"
    return True
```

## _resolve(problem_id)

Returns `(record, QuestionType)` for a stable problem ID. Override
`get_expand_info()` when the expansion needs both values:

```python
def get_expand_info(self, problem_id: str) -> str:
    element, _ = self._resolve(problem_id)
    return f"{element['name']} - Period {element['period']}"
```

## Problem ID Format

IDs are generated as:

```text
{record_id}::{question_key}
```

Reordering records must not change progress. The old index-based format
is retained only as a compatibility migration path.

## QuestionType

| Field       | Type                  | Description |
| ----------- | --------------------- | ----------- |
| `key`       | `str \| None`         | Stable persistence key. Defaults to `label` for legacy packs. |
| `label`     | `str`                 | Human-readable name shown in the question header. |
| `statement` | `(dict) -> str`       | Renders the question text. |
| `answer`    | `(dict) -> str`       | Renders the expected answer. |
| `matcher`   | `(dict, str) -> bool` | Checks user input. |
