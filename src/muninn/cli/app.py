"""CLI command routing and adapters."""

from __future__ import annotations

from collections.abc import Sequence

from ..services.package_manager import PackageManager
from ..services.user_config import ConfigError, UserConfigStore
from .console import ConsolePresenter
from .parser import build_parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    presenter = ConsolePresenter()
    config_store = UserConfigStore()

    if not args.command:
        from ..tui.app import MuninnApp

        MuninnApp(config_store=config_store).run()
        return 0

    manager = PackageManager()

    try:
        if args.command == "new":
            path = manager.create_template(
                args.pack_id,
                args.dir,
                progress=presenter.progress,
            )
            presenter.success(f"Template created at {path}")

        elif args.command == "install":
            pack_id = manager.install_pack(
                args.source,
                progress=presenter.progress,
                force=args.force,
            )
            presenter.success(f"Successfully installed pack '{pack_id}'")

        elif args.command == "uninstall":
            manager.uninstall_pack(
                args.pack_id,
                progress=presenter.progress,
            )
            presenter.success(f"Pack '{args.pack_id}' has been uninstalled.")

        elif args.command == "upgrade":
            if args.pack_id:
                result = manager.upgrade_pack_result(
                    args.pack_id,
                    progress=presenter.progress,
                    force=args.force,
                )
                results = {result.pack_id: result}
            else:
                results = manager.upgrade_all_results(
                    progress=presenter.progress,
                    force=args.force,
                )
            presenter.upgrade_results(results)
            if any(result.failed for result in results.values()):
                return 1

        elif args.command == "list":
            presenter.packs(manager.list_pack_summaries())

        elif args.command == "run":
            from ..tui.app import MuninnApp

            manager.ensure_pack_installed(args.pack_id)
            MuninnApp(
                initial_pack_id=args.pack_id,
                config_store=config_store,
            ).run()

        elif args.command == "group":
            if args.group_command == "list":
                presenter.groups(list(config_store.load().groups))
            elif args.group_command == "run":
                group = _find_group(config_store, args.group)
                from ..tui.app import MuninnApp

                MuninnApp(
                    initial_group_id=group.id,
                    config_store=config_store,
                ).run()
            else:
                parser.print_help()
                return 1

    except Exception as exc:  # noqa: BLE001
        presenter.error(str(exc))
        return 1

    return 0


def _find_group(config_store: UserConfigStore, value: str):
    try:
        groups = config_store.load().groups
    except ConfigError as exc:
        raise ValueError(str(exc)) from exc
    exact_id = next((group for group in groups if group.id == value), None)
    if exact_id is not None:
        return exact_id
    matches = [group for group in groups if group.name.casefold() == value.casefold()]
    if not matches:
        raise ValueError(f"Training group '{value}' was not found.")
    if len(matches) > 1:
        raise ValueError(f"Training group name '{value}' is ambiguous.")
    return matches[0]
