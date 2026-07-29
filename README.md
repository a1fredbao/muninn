# Muninn

Muninn (雾尼) - The Extensible Reciting CLI.

[中文文档](./README_zh.md)

## What is Muninn?

Muninn is a highly extensible CLI application designed to help you memorize anything. Instead of hardcoding questions, Muninn relies on a **Plugin Architecture**. You can easily import "Reciting Packs" created by others (like chemistry elements, GRE vocabulary, or historical events) or develop your own packs using Python.

Muninn acts as a "host" that provides:

1. A **Smart Scheduling Algorithm** (focuses on your weak points).
2. **Persistent State Management** (remembers your progress across sessions).
3. A clean, distraction-free **Terminal UI**.

### Installation & Usage

Install Muninn globally using `uv` (recommended) or `pip`:

```bash
# Using uv (Recommended)
uv tool install muninn

# Or using pip
pip install muninn
```

Available commands:

```bash
# List all imported packs
muninn list

# Import a pack (supports directories or .zip files)
muninn import path/to/pack_or_zip

# Run a specific pack by ID
muninn run <pack_id>

# Generate a new plugin template for development
muninn new <your_new_pack_id>
```

## Plugin Development Guide

Creating your own reciting pack is incredibly easy.

1. **Generate a template**:

   ```bash
   muninn new my_cool_pack
   ```

   This will create a `my_cool_pack` directory containing `manifest.json` and `plugin.py`.

2. **Understand the structure**:
   - `manifest.json`: Metadata for your pack (name, author, version).
   - `plugin.py`: Your custom logic. It must contain a `Plugin` class inheriting from `BaseRecitePlugin`.

3. **Implement the API Contract**:
   Inside `plugin.py`, you will find methods you need to implement. The CLI will provide `self.workspace_dir`, which points to your pack's directory. You can use it to load static assets like `data.csv` or `data.json`.

   - `get_all_problem_ids()`: Return a list of all unique problem IDs.
   - `render_statement(problem_id)`: Return the question text displayed to the user.
   - `check_answer(problem_id, user_input)`: Return `True` if correct, `False` otherwise.
   - `get_expected_display(problem_id)`: Return the correct answer to show when the user gets it wrong.
   - `get_expand_info(problem_id)` (Optional): Return extra trivia to show when the user gets it right.

4. **Test and Import**:

   ```bash
   muninn import ./my_cool_pack
   muninn run my_cool_pack
   ```
