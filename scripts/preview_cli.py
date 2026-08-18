"""Direct wrapper for SQLBuild CLI output previews."""

from __future__ import annotations

from scripts.cli_preview.main.run import run_cli_preview


def main(argv: list[str] | None = None) -> int:
    """Render real SQLBuild CLI output previews."""

    return run_cli_preview(argv)


if __name__ == "__main__":
    raise SystemExit(main())
