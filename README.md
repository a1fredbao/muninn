# Muninn

Muninn (雾尼) - An Extensible Reciting CLI.

[中文文档](./README_zh.md) &nbsp;|&nbsp;[Documentation](https://a1fredbao.github.io/muninn/)

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

| Command                      |                                                               |
| ---------------------------- | ------------------------------------------------------------- |
| `muninn`                     | Open the Textual pack library and management UI.              |
| `muninn install <source>`    | Install a pack (local dir, zip, GitHub URL, or `user/repo`).  |
| `muninn uninstall <pack_id>` | Remove a pack.                                                |
| `muninn upgrade [pack_id]`   | Upgrade one or all packs.                                     |
| `muninn list`                | List installed packs in the traditional CLI.                  |
| `muninn run <pack_id>`       | Open a Textual reciting session for one pack.                 |
| `muninn new <name>`          | Generate a plugin template.                                   |

In the Textual library:

| Key       | Action                                      |
| --------- | ------------------------------------------- |
| `Enter`   | Start the selected pack                     |
| `i`       | Install a pack                              |
| `u`       | Upgrade the selected pack                   |
| `Shift+U` | Upgrade all packs                           |
| `d`       | Uninstall the selected pack                 |
| `r`       | Refresh metadata                            |
| `Ctrl+C`  | Quit the application                        |
| `Ctrl+P`  | Open the command palette                    |

## Write a Plugin

See full documentation at: [a1fredbao.github.io/muninn](https://a1fredbao.github.io/muninn/)
