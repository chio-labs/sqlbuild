"""Direct wrapper for the planner differential harness."""

from __future__ import annotations

from scripts.planner_differential.main.differential import run_planner_differential


def main(argv: list[str] | None = None) -> int:
    """Record or check stateful planner outputs of the corpus across a mutation script."""

    return run_planner_differential(argv)


if __name__ == "__main__":
    raise SystemExit(main())
