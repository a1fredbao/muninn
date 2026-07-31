# Getting Started

## Installation

Install Muninn globally with `uv` (recommended) or `pip`:

```bash
uv tool install muninn-cli
# or
pip install muninn-cli
```

## Basic Commands

```bash
# Install a pack from a local directory, zip file, or GitHub repo
muninn install ./my-pack
muninn install user/repo
muninn install user/repo@v1.0.0
muninn install https://github.com/user/repo

# List installed packs
muninn list

# Run a pack
muninn run <pack_id>

# Uninstall a pack
muninn uninstall <pack_id>

# Create a new plugin template
muninn new <pack_name>
```

## Data Directory

Muninn stores all user data under `~/.muninn/`:

```bash
~/.muninn/
├── packs/         # Installed reciting packs
│   └── chemistry/
└── states/        # Learning progress (SQLite)
    └── chemistry.db
```

Progress is per-pack — uninstalling a pack keeps your data unless you
delete it manually.
