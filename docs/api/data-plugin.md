# DataPlugin

`DataPlugin` is a higher-level wrapper around `BaseRecitePlugin` designed
for the common pattern *"a set of records × a set of question
directions"*.  Declare your question types and Muninn generates all
problem variants automatically.

## Quick Example

``` python
import os, json
from typing import ClassVar
from core.helpers import DataPlugin, QuestionType, Matchers

class Plugin(DataPlugin):
    QUESTION_TYPES: ClassVar[list[QuestionType]] = [
        QuestionType(
            label="Symbol → Name",
            statement=lambda el: f"Element: {el['sym']}",
            answer=lambda el: el["name"],
            matcher=Matchers.case_insensitive("name"),
        ),
        QuestionType(
            label="Name → Number",
            statement=lambda el: f"Element: {el['name']}",
            answer=lambda el: str(el["num"]),
            matcher=Matchers.exact_integer("num"),
        ),
    ]

    def load_records(self) -> list:
        with open(
            os.path.join(self.workspace_dir, "elements.json"), encoding="utf-8"
        ) as f:
            return json.load(f)
```

With 36 elements and 2 question types, this automatically produces 72
problems — no manual ID generation, no dispatch tables.

## `QUESTION_TYPES`

A list of [`QuestionType` objects](#questiontype).  Each represents one
question direction (e.g. "show symbol, ask name").

## `load_records()`

Override to return a list of data dicts from your workspace directory.
Each dict is passed to every `QuestionType`.

## `filter(record, q_type)`

Optional.  Return `False` to skip a particular record × question-type
combination.

``` python
def filter(self, record, q_type):
    if q_type.label == "Position → Element":
        return record["group"] != "0"  # skip noble gases
    return True
```

## `_resolve(problem_id)`

Returns `(record, QuestionType)` for a given problem ID.  Useful when
overriding `get_expand_info()`:

``` python
def get_expand_info(self, problem_id: str) -> str:
    el, qt = self._resolve(problem_id)
    return f"{el['name']} — Period {el['period']}, Group {el['group']}"
```

## Problem ID Format

IDs are generated as `{record_index}__{question_label}`, e.g.
`0__Symbol → Name`.  You generally don't need to interact with them
directly — they're used internally by the scheduler and state manager.

## `QuestionType`

`QuestionType` is a dataclass that encapsulates one question direction:

| Field       | Type                  | Description                                                               |
| ----------- | --------------------- | ------------------------------------------------------------------------- |
| `label`     | `str`                 | Human-readable name, shown in the problem header.                         |
| `statement` | `(dict) -> str`       | Function that renders the question text from a record.                    |
| `answer`    | `(dict) -> str`       | Function that renders the expected answer from a record.                  |
| `matcher`   | `(dict, str) -> bool` | Function that checks user input. Use [`Matchers`](matchers.md) factories. |
