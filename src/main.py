"""Package entry point."""

from src.cli.app import run_cli


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
