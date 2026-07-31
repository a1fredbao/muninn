# Plugin Development

Muninn plugins are self-contained Python packages.  Every plugin must
provide a `manifest.json` and a `plugin.py` with a class that implements
the plugin contract.

Muninn offers **three levels of abstraction**, from zero-boilerplate to
full control.

| Level                                    | Best for                                          |
| ---------------------------------------- | ------------------------------------------------- |
| [`FlashcardPlugin`](api/flashcard.md)    | Simple front/back cards (vocabulary, definitions) |
| [`DataPlugin`](api/data-plugin.md)       | Structured data quizzed from multiple angles      |
| [`BaseRecitePlugin`](api/base-plugin.md) | Full control over every aspect                    |

## Getting Started

1. Generate a template: `muninn new my-pack`
2. Choose your plugin level and edit `plugin.py`.
3. Install and test: `muninn install ./my-pack && muninn run my-pack`

## Pack Layout

    my-pack/
    ├── manifest.json   # Package metadata
    ├── plugin.py        # Core logic
    ├── data.csv         # Static data (optional — whatever your plugin needs)
    └── data.json        # Alternative data format

## manifest.json

    {
        "id": "my-pack",
        "name": "My Pack",
        "author": "Your Name",
        "version": "1.0.0",
        "description": "A brief description."
    }

| Field         | Required | Notes                                          |
| ------------- | -------- | ---------------------------------------------- |
| `id`          | Yes      | Unique identifier, used as the install target. |
| `name`        | Yes      | Human-readable display name.                   |
| `author`      | No       |                                                |
| `version`     | Yes      | SemVer.                                        |
| `description` | No       |                                                |
