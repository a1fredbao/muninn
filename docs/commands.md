# Command Reference

## `muninn install`

Install a reciting pack.

```bash
muninn install <source>
```

`<source>` accepts:

| Format                    | Example                                 |
| ------------------------- | --------------------------------------- |
| Local directory           | `./my-pack` or `/abs/path`              |
| Local `.zip` file         | `./my-pack.zip`                         |
| GitHub shorthand          | `user/repo` (defaults to `main` branch) |
| GitHub shorthand + branch | `user/repo@dev`                         |
| Full GitHub URL           | `https://github.com/user/repo`          |

The pack is copied to `~/.muninn/packs/<pack_id>/`.  Installing the same
`pack_id` again overwrites the previous version.

Muninn records the installation source in the pack's `manifest.json` so
that `muninn upgrade` knows where to check for updates later.

### Dependencies

If a pack includes a `requirements.txt` at its root, Muninn installs
those packages into a shared virtual environment at `~/.muninn/venv/`.
No manual `pip install` step is required — the next `muninn run` will
find the installed packages automatically.

This is designed for packs that need third-party libraries (e.g. `openai`
for AI-powered answer checking, `requests` for fetching live data).  The
shared venv keeps plugin dependencies isolated from your system Python.

## `muninn upgrade`

Check for and install newer versions of installed packs.

```bash
# Upgrade all installed packs
muninn upgrade

# Upgrade a specific pack
muninn upgrade <pack_id>
```

How it works:

| Source type                 | Upgrade strategy                                                                                                                    |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| GitHub (`github:user/repo`) | Fetches `manifest.json` from the repository's default branch. If the remote version is newer, the pack is re-installed from GitHub. |
| Local path (`local:/path`)  | Reads `manifest.json` from the source directory. If it no longer exists, the pack is skipped with a warning.                        |

Packs installed before Muninn 0.3.0 do not have a `source` field and
cannot be upgraded — reinstall them with `muninn install` to enable
upgrades.

## `muninn uninstall`

Remove a previously installed pack.

```bash
muninn uninstall <pack_id>
```

Deletes `~/.muninn/packs/<pack_id>/`.  Progress data in
`~/.muninn/states/<pack_id>.db` is **not** deleted — you can reinstall
later and pick up where you left off.

## `muninn list`

List all installed packs with their metadata (id, name, author, version).

```bash
muninn list
```

## `muninn run`

Start a reciting session for a pack.

```bash
muninn run <pack_id>
```

The scheduler presents problems based on your historical accuracy and
response time, favouring topics you struggle with.

During a session:

- Type your answer and press Enter.
- Type `q` or press `Ctrl+C` to quit and see your session summary.

## `muninn new`

Generate a new plugin template in the current directory.

```bash
muninn new <pack_name>
```

Creates a `<pack_name>/` folder containing:

- `manifest.json` — pack metadata
- `plugin.py` — a skeleton `DataPlugin` with import scaffolding
