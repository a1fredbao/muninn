# Pack Specification

A Muninn pack is a directory containing at minimum a `manifest.json` and
a `plugin.py`.

## Directory Structure

``` bash
my-pack/
├── manifest.json      # Required: pack metadata
├── plugin.py           # Required: plugin logic
├── data.csv            # Optional: static data
└── data.json           # Optional: static data
```

Pack IDs must be unique across a user's installation.  Installing a pack
with the same ID as an existing one overwrites the previous version.

## `manifest.json`

``` json
{
    "id": "my-pack",
    "name": "My Pack",
    "author": "Your Name",
    "version": "1.0.0",
    "description": "A brief description."
}
```

| Field         | Type   | Required | Description                                                                |
| ------------- | ------ | -------- | -------------------------------------------------------------------------- |
| `id`          | string | Yes      | Unique identifier. Must match the directory name under `~/.muninn/packs/`. |
| `name`        | string | Yes      | Human-readable display name.                                               |
| `author`      | string | No       | Author name or handle.                                                     |
| `version`     | string | Yes      | Semantic version (`MAJOR.MINOR.PATCH`).                                    |
| `description` | string | No       | Short description of the pack's content.                                   |

## Distribution

Packs can be distributed as:

- A plain directory (`muninn install ./my-pack`)
- A `.zip` archive (`muninn install ./my-pack.zip`)
- A GitHub repository (`muninn install user/repo`)

For GitHub distribution, the repository root must contain `manifest.json`
and `plugin.py` at the top level (with data files alongside them).
Muninn uses GitHub's archive API to fetch the zip, so the standard
`https://github.com/user/repo/archive/refs/heads/main.zip` URL is used
automatically — no git installation is required on the user's machine.
Note: only branch references are supported; git tags cannot be resolved.
