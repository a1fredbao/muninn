"""Command-line argument parsing."""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version


def _package_version() -> str:
    try:
        return version("muninn-cli")
    except PackageNotFoundError:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muninn",
        description="Muninn - The Extensible Training CLI",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"Muninn {_package_version()}",
    )

    subparsers = parser.add_subparsers(dest="command")

    parser_new = subparsers.add_parser(
        "new",
        help="Create a new plugin template",
    )
    parser_new.add_argument("pack_id", help="The ID/name of the new pack")
    parser_new.add_argument(
        "--dir",
        default=".",
        help="Directory to create the template in",
    )

    parser_install = subparsers.add_parser(
        "install",
        help="Install a pack from a directory, zip file, or GitHub URL",
    )
    parser_install.add_argument(
        "source",
        help="Pack directory, zip file, or GitHub repository",
    )

    parser_uninstall = subparsers.add_parser(
        "uninstall",
        help="Uninstall a previously installed pack",
    )
    parser_uninstall.add_argument("pack_id", help="The ID of the pack to uninstall")

    parser_upgrade = subparsers.add_parser(
        "upgrade",
        help="Upgrade installed packs to the latest version",
    )
    parser_upgrade.add_argument(
        "pack_id",
        nargs="?",
        help="The ID of a specific pack to upgrade",
    )

    subparsers.add_parser("list", help="List all installed packs")

    parser_run = subparsers.add_parser("run", help="Run a training pack")
    parser_run.add_argument("pack_id", help="The ID of the pack to run")

    return parser
