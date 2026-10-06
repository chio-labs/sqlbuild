"""Direct wrapper for the compiler engine differential harness."""

from __future__ import annotations

from scripts.compiler_differential.main.differential import run_compiler_differential


def main(argv: list[str] | None = None) -> int:
    """Compare compile and plan output between the Python and native compiler engines."""

    return run_compiler_differential(argv)


if __name__ == "__main__":
    raise SystemExit(main())
