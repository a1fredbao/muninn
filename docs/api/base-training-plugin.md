# BaseTrainingPlugin

`BaseTrainingPlugin` is the plugin entry point. Its main responsibility is
to expose independently selectable `QuestionType` objects.

```python
from muninn.plugin_api import BaseTrainingPlugin


class QuestionType:
    key = "capital-to-country"
    label = "Capital -> Country"
    description = "Identify the country from its capital."

    def get_all_problem_ids(self) -> list[str]:
        return ["france", "japan"]

    def describe_problem(self, problem_id: str):
        return {"tags": ["geography"], "difficulty": 0.3}

    def render_statement(self, problem_id: str) -> str:
        return "Paris"

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        return user_input.strip().casefold() == "france"

    def get_expected_display(self, problem_id: str) -> str:
        return "France"

    def get_expand_info(self, problem_id: str) -> str:
        return "Paris is the capital of France."


class Plugin(BaseTrainingPlugin):
    def get_question_types(self):
        return [QuestionType()]
```

## QuestionType contract

| Method | Purpose |
| --- | --- |
| `get_all_problem_ids()` | Return stable IDs local to this question type. |
| `describe_problem()` | Return scheduling metadata such as tags, difficulty, and estimated time. |
| `render_statement()` | Render the prompt. |
| `check_answer()` | Judge an attempt. |
| `allow_user_acceptance` | Optional flag: ask the user to confirm a strict mismatch. |
| `get_expected_display()` | Return the expected answer. |
| `get_expand_info()` | Return optional post-answer guidance. |

## Optional user acceptance

If an exact matcher may reject a valid paraphrase, set
`allow_user_acceptance = True` on the question type. When
`check_answer()` returns `False`, Muninn shows the user's answer and the
expected answer, then asks the user to confirm whether it is acceptable.

```python
class QuestionType:
    allow_user_acceptance = True
```

The confirmation decision is stored per problem and answer. Accepted
answers count as correct; rejected answers remain wrong. Repeating the
same answer reuses the stored decision instead of asking again.

The host hashes the pack ID, question-type key, and local problem ID into
an opaque global problem key. Group configuration stores these hashes
rather than raw user-controlled paths.

## Lifecycle

1. Muninn constructs the plugin with `workspace_dir`.
2. Muninn calls `initialize(context)`.
3. Muninn calls `get_question_types()`.
4. Selected question types expose their problem IDs and metadata.
5. Attempts are routed back to the owning question type.
6. Muninn calls `close()` when the session ends.

The plugin runs in an isolated worker process. Dependencies are loaded
from the pack's versioned environment.
