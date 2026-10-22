"""Direct wrapper for the native stub drift check."""

from __future__ import annotations

from scripts.native_stub.main.check import run_native_stub_check


def main(argv: list[str] | None = None) -> int:
    """Check the native stub declares only registered names."""
    return run_native_stub_check(argv)


if __name__ == "__main__":
    raise SystemExit(main())
