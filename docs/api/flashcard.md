# FlashcardPlugin

`FlashcardPlugin` is the simplest plugin type.  It handles the entire
"front → back" flashcard pattern with zero boilerplate.

## Quickstart

Create a CSV with `front` and `back` columns:

```csv
front,back
apple,苹果
dog,狗
cat,猫
```

Then write a 3-line plugin:

```python
from core.helpers import FlashcardPlugin


class Plugin(FlashcardPlugin):
    DATA_FILE = "words.csv"
```

That's it.  `FlashcardPlugin` automatically:

- Loads `words.csv` from the workspace directory.
- Generates one problem per row.
- Renders `front` as the question, checks against `back`.

## Supported Formats

| Extension | Format                                                   |
| --------- | -------------------------------------------------------- |
| `.csv`    | CSV with `front` and `back` columns.                     |
| `.json`   | JSON array of `{"front": "...", "back": "..."}` objects. |

## Customisation

Override `get_expand_info()` to show extra context on correct answers:

```python
class Plugin(FlashcardPlugin):
    DATA_FILE = "words.csv"

    def get_expand_info(self, problem_id: str) -> str:
        record, _ = self._resolve(problem_id)
        return record.get("example", "")
```

## File Layout

```bash
my-flashcards/
├── manifest.json
├── plugin.py        # 3 lines
└── words.csv        # front, back columns
```
