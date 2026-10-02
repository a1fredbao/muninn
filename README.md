# Muninn

Muninn (雾尼) - An Extensible Training CLI.

[中文文档](./README_zh.md) &nbsp;|&nbsp;[Documentation](https://a1fredbao.github.io/muninn/)

## What is Muninn?

Muninn is a highly extensible CLI application designed to train memory and problem-solving skills. Instead of hardcoding questions, Muninn relies on a **Plugin Architecture**. You can install "Training Packs" created by others (like chemistry elements, GRE vocabulary, or historical events) or develop your own packs using Python.

Muninn acts as a "host" that provides:

1. A **Smart Scheduling Algorithm** (focuses on your weak-points).
2. **Persistent State Management** (remembers your progress across sessions).
3. A clean, distraction-free **Terminal UI**.

## Installation & Usage

Install Muninn globally using `uv` (recommended) or `pip`:

```bash
# Using uv (Recommended)
uv tool install muninn-cli

# Or using pip
pip install muninn-cli
```

## Quickstart

```bash
# Install a pack from GitHub
muninn install a1fredbao/muninn-chemistry-plugin

# Open the Textual library
muninn

# Or start a specific pack directly
muninn run muninn-chemistry-plugin
```

## Commands

| Command                      |                                                              |
| ---------------------------- | ------------------------------------------------------------ |
| `muninn`                     | Open the Textual pack library and management UI.             |
| `muninn install <source>`    | Install a pack (local dir, zip, GitHub URL, or `user/repo`). |
| `muninn uninstall <pack_id>` | Remove a pack.                                               |
| `muninn upgrade [pack_id]`   | Upgrade one or all packs.                                    |
| `muninn list`                | List installed packs in the traditional CLI.                 |
| `muninn run <pack_id>`       | Open a Textual training session for one pack.                |
| `muninn new <name>`          | Generate a plugin template.                                  |
| `muninn group list`          | List saved training groups.                                  |
| `muninn group run <group>`   | Open a saved training group.                                 |

In the Textual library:

| Key       | Action                                   |
| --------- | ---------------------------------------- |
| `Enter`   | Start the selected pack                  |
| `i`       | Install a pack                           |
| `u`       | Upgrade the selected pack                |
| `Shift+U` | Upgrade all packs                        |
| `d`       | Uninstall the selected pack              |
| `r`       | Refresh metadata                         |
| `g`       | Open the training group builder          |
| `/`       | Search packs, groups, and question types |
| `Ctrl+T`  | Search and change the Textual theme      |
| `Ctrl+C`  | Quit the application                     |
| `Ctrl+P`  | Open the command palette                 |

While answering, `Enter` submits the answer and `Ctrl+Enter` inserts a
newline. `Command+Enter` also inserts a newline in terminals that forward
the Command modifier to the application. The answer field grows with its
contents, then scrolls internally when it reaches half of the available
session height.

A training group combines selected question types from any number of
installed packs. Group selections and the active theme are stored in
`~/.muninn/config.json`.

## Write a Plugin

See full documentation at: [muninn.alfredbao.cn](https://muninn.alfredbao.cn/) or [the deepwiki page of Muninn](https://deepwiki.com/a1fredbao/muninn/).
