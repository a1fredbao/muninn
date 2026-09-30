# FlashcardPlugin

`FlashcardPlugin` is the simplest plugin type.  It handles the entire
"front → back" flashcard pattern with zero boilerplate.

## Quickstart

Create a CSV with `front` and `back` columns:

``` csv
front,back
apple,苹果
dog,狗
cat,猫
```

Then write a 3-line plugin:

``` python
from muninn.core.helpers import FlashcardPlugin


class Plugin(FlashcardPlugin):
    DATA_FILE = "words.csv"
```

Flashcards use `id`, then `front`, as their stable record key. Include
an explicit `id` column when two cards can share the same front text.

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

Set `EXPAND_FIELD` to show another CSV or JSON field after a correct
answer:

``` python
class Plugin(FlashcardPlugin):
    DATA_FILE = "words.csv"
    EXPAND_FIELD = "example"
```

## File Layout

``` bash
my-flashcards/
├── manifest.json
├── plugin.py        # 3 lines
└── words.csv        # front, back columns
```
