#!/usr/bin/env python3
"""Bump the muninn-cli version, regenerate the lockfile, commit, and tag.

Usage:
  python scripts/bump_version.py --patch          # 0.1.0 -> 0.1.1
  python scripts/bump_version.py --minor          # 0.1.0 -> 0.2.0
  python scripts/bump_version.py --major          # 0.1.0 -> 1.0.0
  python scripts/bump_version.py -v 1.5.0         # set exact version
  python scripts/bump_version.py --patch --push   # also push the tag
  python scripts/bump_version.py --patch --dry-run # preview only
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
LOCKFILE = ROOT / "uv.lock"
VERSION_RE = re.compile(r'^(version\s*=\s*)"([^"]+)"', re.MULTILINE)


def read_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = VERSION_RE.search(text)
    if not m:
        sys.exit("❌ Could not find 'version = \"...\"' in pyproject.toml")
    return m.group(2)


def bump_version(current: str, part: str) -> str:
    parts = [int(x) for x in current.split(".")]
    if len(parts) != 3:
        sys.exit(f"❌ Version '{current}' is not in MAJOR.MINOR.PATCH format.")
    if part == "major":
        return f"{parts[0] + 1}.0.0"
    if part == "minor":
        return f"{parts[0]}.{parts[1] + 1}.0"
    if part == "patch":
        return f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
    sys.exit(f"❌ Unknown bump part: {part}")


def write_version(new_version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    updated, count = VERSION_RE.subn(f'\\1"{new_version}"', text)
    if count != 1:
        sys.exit("❌ Expected exactly one version line in pyproject.toml.")
    PYPROJECT.write_text(updated, encoding="utf-8")


def run(cmd: list[str], **kwargs) -> None:
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=ROOT, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump muninn-cli version")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--patch", action="store_true", help="Bump patch (0.1.0 -> 0.1.1)"
    )
    group.add_argument(
        "--minor", action="store_true", help="Bump minor (0.1.0 -> 0.2.0)"
    )
    group.add_argument(
        "--major", action="store_true", help="Bump major (0.1.0 -> 1.0.0)"
    )
    group.add_argument(
        "-v", "--version", type=str, help="Set exact version (e.g. 1.5.0)"
    )
    parser.add_argument("--push", action="store_true", help="Push tag after bumping")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only, no changes"
    )
    args = parser.parse_args()

    old = read_version()

    if args.version:
        new = args.version
    elif args.patch:
        new = bump_version(old, "patch")
    elif args.minor:
        new = bump_version(old, "minor")
    else:
        new = bump_version(old, "major")

    print(f"Bumping: {old} -> {new}")

    if args.dry_run:
        print("(dry run — no files changed)")
        return

    # 1. Update pyproject.toml
    write_version(new)
    print(f"✅ Updated {PYPROJECT.relative_to(ROOT)}")

    # 2. Regenerate lockfile so uv.lock records the new version
    run(["uv", "lock"])
    print(f"✅ Regenerated {LOCKFILE.relative_to(ROOT)}")

    # 3. Commit both pyproject.toml and uv.lock
    run(
        [
            "git",
            "add",
            str(PYPROJECT.relative_to(ROOT)),
            str(LOCKFILE.relative_to(ROOT)),
        ]
    )
    run(["git", "commit", "-m", f"chore: bump version to {new}"])

    # 4. Tag
    run(["git", "tag", "-a", f"v{new}", "-m", f"Release v{new}"])

    print(f"✅ Committed and tagged v{new}")

    if args.push:
        run(["git", "push", "origin", "HEAD"])
        run(["git", "push", "origin", f"v{new}"])
        print(f"🚀 Pushed commit + tag v{new} to origin")
    else:
        print("\nTo push:  git push origin HEAD && git push origin v" + new)


if __name__ == "__main__":
    main()
