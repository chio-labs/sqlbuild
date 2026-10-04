"""Direct wrapper for same-runner compile performance comparison."""

from __future__ import annotations

from scripts.compile_performance_ratio.main.compare import compare_compile_performance


def main(argv: list[str] | None = None) -> int:
    """Compare base and head compiles on the same machine."""

    return compare_compile_performance(argv)


if __name__ == "__main__":
    raise SystemExit(main())
