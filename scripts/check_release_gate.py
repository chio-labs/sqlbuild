"""Direct wrapper for the release pull request Verify gate check."""

from __future__ import annotations

from scripts.release_gate.main.check import run_release_gate_check


def main(argv: list[str] | None = None) -> int:
    """Check the release pull request Verify gate."""
    return run_release_gate_check(argv)


if __name__ == "__main__":
    raise SystemExit(main())
