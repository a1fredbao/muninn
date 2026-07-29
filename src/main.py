import argparse
import sys
import traceback

from src.cli.manager import PackageManager
from src.cli.runner import GameRunner


def main():
    parser = argparse.ArgumentParser(description="Muninn - The Extensible Reciting CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: new
    parser_new = subparsers.add_parser("new", help="Create a new plugin template")
    parser_new.add_argument("pack_id", type=str, help="The ID/name of the new pack")
    parser_new.add_argument(
        "--dir", type=str, default=".", help="Directory to create the template in"
    )

    # Command: import
    parser_import = subparsers.add_parser(
        "import", help="Import a pack from a directory or zip file"
    )
    parser_import.add_argument(
        "path", type=str, help="Path to the pack directory or .zip file"
    )

    # Command: list
    subparsers.add_parser("list", help="List all imported packs")

    # Command: run
    parser_run = subparsers.add_parser("run", help="Run a reciting pack")
    parser_run.add_argument("pack_id", type=str, help="The ID of the pack to run")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    manager = PackageManager()

    if args.command == "new":
        try:
            manager.create_template(args.pack_id, args.dir)
        except Exception as e:  # noqa: BLE001
            print(f"❌ Failed to create template: {e}")

    elif args.command == "import":
        try:
            manager.import_pack(args.path)
        except Exception as e:  # noqa: BLE001
            print(f"❌ Failed to import pack: {e}")

    elif args.command == "list":
        packs = manager.list_packs()
        if not packs:
            print("No packs imported yet. Use 'muninn import <path>' to add one.")
        else:
            print(f"=== Installed Packs ({len(packs)}) ===")
            for p in packs:
                print(
                    f"- {p.get('id')} (v{p.get('version')}): {p.get('name')} by {p.get('author')}"
                )

    elif args.command == "run":
        try:
            plugin = manager.load_plugin(args.pack_id)
            runner = GameRunner(args.pack_id, plugin)
            runner.run()
        except Exception as e:  # noqa: BLE001
            print(f"❌ Failed to run pack '{args.pack_id}': {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
