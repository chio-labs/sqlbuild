"""Direct wrapper for the build feature alignment check."""

from __future__ import annotations

from scripts.build_features.main.check import run_build_features_check


def main(argv: list[str] | None = None) -> int:
    """Check that the sqb and extension builds share every common crate."""
    return run_build_features_check(argv)


if __name__ == "__main__":
    raise SystemExit(main())
