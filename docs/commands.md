# Command Reference

## `muninn install`

Install a reciting pack.

``` bash
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

The pack is copied to `~/.muninn/packs/<pack_id>/`. Installing the same
`pack_id` again overwrites the previous version.

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

``` bash
muninn list
```

## `muninn run`

Start a reciting session for a pack.

``` bash
muninn run <pack_id>
```

The scheduler presents problems based on your historical accuracy and
response time, favouring topics you struggle with.

During a session:

- Type your answer and press Enter.
- Type `q` or press `Ctrl+C` to quit and see your session summary.

## `muninn new`

Generate a new plugin template in the current directory.

``` bash
muninn new <pack_name>
```

Creates a `<pack_name>/` folder containing:

- `manifest.json` — pack metadata
- `plugin.py` — a skeleton `DataPlugin` with import scaffolding
