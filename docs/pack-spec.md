# Pack Specification

A Muninn pack is a directory containing at minimum a `manifest.json` and
a `plugin.py`.

## Directory Structure

``` bash
my-pack/
├── manifest.json       # Required: pack metadata
├── plugin.py           # Required: plugin logic
├── requirements.txt    # Optional: pip dependencies
├── data.csv            # Optional: static data
└── data.json           # Optional: static data
```

Pack IDs must be unique across a user's installation.  Installing a pack
with the same ID as an existing one overwrites the previous version.

## `manifest.json`

```json
{
    "id": "my-pack",
    "name": "My Pack",
    "author": "Your Name",
    "version": "1.0.0",
    "description": "A brief description.",
    "entrypoint": "plugin:Plugin",
    "api_version": "1"
}
```

| Field         | Type   | Required | Description                                                                                                                                                                                                   |
| ------------- | ------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`          | string | Yes      | Unique identifier. Must match the directory name under `~/.muninn/packs/`.                                                                                                                                    |
| `name`        | string | Yes      | Human-readable display name.                                                                                                                                                                                  |
| `author`      | string | No       | Author name or handle.                                                                                                                                                                                        |
| `version`     | string | Yes      | Semantic version (`MAJOR.MINOR.PATCH`).                                                                                                                                                                       |
| `description` | string | No       | Short description of the pack's content.                                                                                                                                                                      |
| `source`      | string | Auto     | Set by Muninn on install. Tracks where the pack came from so `muninn upgrade` knows where to check for updates. One of `local:<abspath>`, `github:user/repo`, or `github:user/repo@ref`. Do not set manually. |
| `entrypoint`  | string | Yes      | Plugin class location in `module:ClassName` form.                                                                                                                                                             |
| `api_version` | string | Yes      | Plugin API version. Current version is `1`; missing values are treated as legacy `0`.                                                                                                                        |

Record IDs and question keys must be stable across pack updates. Muninn
uses `<record_id>::<question_key>` as the persistent progress key.

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

## Upgrades

When a pack is installed, Muninn records the installation source in
`manifest.json`.  This enables `muninn upgrade <pack_id>` (or
`muninn upgrade` to upgrade all packs) to:

1. Read `manifest.json` from the recorded source (local path or GitHub).
2. Compare the source version against the installed version.
3. Re-install the pack if the source version is newer.

Pack authors should [bump the `version` field](https://semver.org/)
whenever they publish changes — that is the signal Muninn uses to
determine whether an upgrade is available.

## Dependencies

If your plugin needs third-party Python packages, place a standard
`requirements.txt` at the root of your pack:

``` text
openai>=1.0.0
httpx>=0.27.0
```

Muninn creates a versioned isolated virtual environment at
`~/.muninn/venvs/<pack_id>/<version>/` for each pack and installs the
declared packages there automatically. Each training session runs the
plugin in a dedicated worker process with that environment.

If dependency installation fails (e.g. a typo in the package name, a
network error), Muninn does **not** replace the pack.  The existing
version stays in place and an error message is printed.
