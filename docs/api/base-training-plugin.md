# BaseTrainingPlugin

`BaseTrainingPlugin` is the lowest-level plugin interface. Implement all
five methods for full control over rendering, answer checking, and
metadata display. New plugins should import it from the stable
`muninn.plugin_api` namespace.

``` python
from muninn.plugin_api import BaseTrainingPlugin


class Plugin(BaseTrainingPlugin):
    def load_data(self):
        """Load static data from ``self.workspace_dir``.  Called once
        at initialisation."""
        pass

    def get_all_problem_ids(self) -> list[str]:
        """Return every unique problem ID in this pack."""
        pass

    def render_statement(self, problem_id: str) -> str:
        """Return the question text shown to the user."""
        pass

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        """Return ``True`` if *user_input* is correct."""
        pass

    def get_expected_display(self, problem_id: str) -> str:
        """Return the correct answer to show on failure."""
        pass

    def get_expand_info(self, problem_id: str) -> str:
        """Optional: return extra info to show on success."""
        return ""
```

`check_answer()` may also be asynchronous.  Muninn awaits async plugin
methods directly and runs synchronous methods in a background worker so
the Textual interface remains responsive:

``` python
async def check_answer(
    self,
    problem_id: str,
    user_input: str,
) -> bool:
    result = await call_remote_judge(problem_id, user_input)
    return result.accepted
```

## Lifecycle

1. Muninn constructs the plugin with `workspace_dir`.
2. Muninn calls `initialize(context)`.
3. Muninn calls `get_all_problem_ids()` to build the scheduler queue.
4. For each problem, Muninn calls `render_statement()` -> captures user
   input -> calls `check_answer()`.
5. On correct answer: `get_expand_info()` is shown.
6. On wrong answer: `get_expected_display()` is shown.
7. Muninn calls `close()` when the session ends.


## `workspace_dir`

`self.workspace_dir` points to the pack's private directory under
`~/.muninn/packs/<pack_id>/`.  Use it to load static assets like CSV or
JSON files:

``` python
def load_data(self):
    import json, os

    path = os.path.join(self.workspace_dir, "data.json")
    with open(path, encoding="utf-8") as f:
        self.records = json.load(f)
```
