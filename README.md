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

# Start reciting
muninn run muninn-chemistry-plugin
```

## Commands

| Command                      |                                                              |
| ---------------------------- | ------------------------------------------------------------ |
| `muninn install <source>`    | Install a pack (local dir, zip, GitHub URL, or `user/repo`). |
| `muninn uninstall <pack_id>` | Remove a pack.                                               |
| `muninn list`                | List installed packs.                                        |
| `muninn run <pack_id>`       | Start a reciting session.                                    |
| `muninn new <name>`          | Generate a plugin template.                                  |

## Write a Plugin

See full documentation at: [a1fredbao.github.io/muninn](https://a1fredbao.github.io/muninn/)
