"""Tests for new CLI package and group options."""

from muninn.cli.parser import build_parser


def test_install_and_upgrade_accept_force():
    parser = build_parser()

    install = parser.parse_args(["install", "user/repo", "--force"])
    upgrade = parser.parse_args(["upgrade", "pack", "--force"])

    assert install.force
    assert upgrade.force


def test_group_commands_parse():
    parser = build_parser()

    listed = parser.parse_args(["group", "list"])
    run = parser.parse_args(["group", "run", "my-group"])

    assert listed.group_command == "list"
    assert run.group_command == "run"
    assert run.group == "my-group"
