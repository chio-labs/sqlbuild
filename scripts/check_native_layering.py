"""Direct wrapper for the native crate layering check."""

from __future__ import annotations

from scripts.native_layering.main.check import run_native_layering_check


def main(argv: list[str] | None = None) -> int:
    """Check native crate layering."""
    return run_native_layering_check(argv)


if __name__ == "__main__":
    raise SystemExit(main())
