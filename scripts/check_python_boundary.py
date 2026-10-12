"""Direct wrapper for the Python boundary ratchet."""

from __future__ import annotations

from scripts.python_boundary.main.check import run_python_boundary_check


def main(argv: list[str] | None = None) -> int:
    """Check the Python boundary ratchet."""
    return run_python_boundary_check(argv)


if __name__ == "__main__":
    raise SystemExit(main())
