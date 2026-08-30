"""Direct wrapper for pull request metadata validation."""

from __future__ import annotations

from scripts.pr_metadata.main.validate import run_pr_metadata_validation


def main(argv: list[str] | None = None) -> int:
    """Validate pull request metadata."""
    return run_pr_metadata_validation(argv)


if __name__ == "__main__":
    raise SystemExit(main())
