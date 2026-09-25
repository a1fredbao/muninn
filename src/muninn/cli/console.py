"""Rich-powered console presentation for the traditional CLI."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..services.manifest import PackSummary
from ..services.package_manager import PackageProgress, UpgradeResult


class ConsolePresenter:
    def __init__(self) -> None:
        self.stdout = Console(file=sys.stdout)
        self.stderr = Console(file=sys.stderr)

    def progress(self, event: PackageProgress) -> None:
        self.stderr.print(f"[dim]{escape(event.message)}[/dim]")

    def success(self, message: str) -> None:
        self.stdout.print(f"[green]{escape(message)}[/green]")

    def warning(self, message: str) -> None:
        self.stderr.print(f"[yellow]{escape(message)}[/yellow]")

    def error(self, message: str) -> None:
        self.stderr.print(f"[red]Error:[/red] {escape(message)}")

    def packs(self, packs: list[dict] | list[PackSummary]) -> None:
        if not packs:
            self.stdout.print("No packs installed yet. Use 'muninn install <source>'.")
            return

        table = Table(title=f"Installed Packs ({len(packs)})")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name")
        table.add_column("Version", justify="right")
        table.add_column("Author")
        table.add_column("Description")

        for pack in sorted(
            packs,
            key=lambda item: (
                item.pack_id
                if isinstance(item, PackSummary)
                else str(item.get("id", ""))
            ),
        ):
            if isinstance(pack, PackSummary):
                table.add_row(
                    escape(pack.pack_id),
                    escape(pack.name if pack.valid else "Invalid pack"),
                    escape(pack.version),
                    escape(pack.author),
                    escape(pack.error or pack.description),
                )
            else:
                table.add_row(
                    escape(str(pack.get("id", ""))),
                    escape(str(pack.get("name", ""))),
                    escape(str(pack.get("version", ""))),
                    escape(str(pack.get("author") or "")),
                    escape(str(pack.get("description") or "")),
                )
        self.stdout.print(table)

    def upgrade_results(self, results: dict[str, UpgradeResult]) -> None:
        if not results:
            self.stdout.print("No packs installed.")
            return

        for result in results.values():
            if result.status == "upgraded":
                self.stdout.print(
                    f"[green]Upgraded {escape(str(result.pack_id))}: "
                    f"{escape(str(result.current_version))} -> "
                    f"{escape(str(result.remote_version))}[/green]"
                )
            elif result.status == "current":
                self.stdout.print(
                    f"{escape(str(result.pack_id))} "
                    f"({escape(str(result.current_version))}) is up to date."
                )
            elif result.status == "skipped":
                self.warning(result.error or f"Skipped {result.pack_id}.")
            else:
                self.error(result.error or f"Failed to upgrade {result.pack_id}.")
