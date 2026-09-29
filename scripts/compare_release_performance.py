"""Direct wrapper for comparing a release candidate with the previous published release."""

from __future__ import annotations

from scripts.release_performance.main.compare import compare_release_performance


def main(argv: list[str] | None = None) -> int:
    """Compare candidate and baseline command performance on the same machine."""

    return compare_release_performance(argv)


if __name__ == "__main__":
    raise SystemExit(main())
