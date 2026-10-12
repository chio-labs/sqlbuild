"""Direct wrapper for the compiler differential harness."""

from __future__ import annotations

from scripts.compiler_differential.main.differential import run_compiler_differential


def main(argv: list[str] | None = None) -> int:
    """Check compile and plan output of the corpus against its expectations and goldens."""

    return run_compiler_differential(argv)


if __name__ == "__main__":
    raise SystemExit(main())
