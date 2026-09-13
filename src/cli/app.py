"""CLI command routing and adapters."""

from __future__ import annotations

from collections.abc import Sequence

from ..services.package_manager import PackageManager
from .console import ConsolePresenter
from .parser import build_parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    presenter = ConsolePresenter()

    if not args.command:
        from ..tui.app import MuninnApp

        MuninnApp().run()
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
                )
                results = {result.pack_id: result}
            else:
                results = manager.upgrade_all_results(progress=presenter.progress)
            presenter.upgrade_results(results)
            if any(result.failed for result in results.values()):
                return 1

        elif args.command == "list":
            presenter.packs(manager.list_packs())

        elif args.command == "run":
            from ..tui.app import MuninnApp

            manager.ensure_pack_installed(args.pack_id)
            MuninnApp(initial_pack_id=args.pack_id).run()

    except Exception as exc:  # noqa: BLE001
        presenter.error(str(exc))
        return 1

    return 0
