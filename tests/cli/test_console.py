"""Regression tests for safe Rich markup rendering."""

from src.cli.console import ConsolePresenter
from src.services.package_manager import UpgradeResult


def test_dynamic_status_messages_are_rendered_as_literal_text(capsys):
    presenter = ConsolePresenter()

    presenter.error("[red]not markup[/red] [broken]")
    presenter.warning("[yellow]warning[/yellow]")
    presenter.success("[green]success[/green]")

    captured = capsys.readouterr()
    assert "[red]not markup[/red] [broken]" in captured.err
    assert "[yellow]warning[/yellow]" in captured.err
    assert "[green]success[/green]" in captured.out


def test_pack_metadata_is_rendered_as_literal_text(capsys):
    presenter = ConsolePresenter()
    presenter.packs(
        [
            {
                "id": "[id]",
                "name": "[name]",
                "version": "[version]",
                "author": "[author]",
                "description": "[description]",
            }
        ]
    )

    captured = capsys.readouterr()
    assert "[id]" in captured.out
    assert "[name]" in captured.out
    assert "[version]" in captured.out
    assert "[author]" in captured.out
    assert "[description]" in captured.out


def test_upgrade_metadata_is_rendered_as_literal_text(capsys):
    presenter = ConsolePresenter()
    presenter.upgrade_results(
        {
            "pack": UpgradeResult(
                pack_id="[red]pack[/red]",
                status="upgraded",
                current_version="[broken]",
                remote_version="[green]2.0[/green]",
            )
        }
    )

    captured = capsys.readouterr()
    assert "[red]pack[/red]" in captured.out
    assert "[broken]" in captured.out
    assert "[green]2.0[/green]" in captured.out
