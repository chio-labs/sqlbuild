"""Reproducible local Rules benchmark command."""

from scripts.rules_benchmark.main.run import run_rules_benchmark


def main() -> int:
    """Run the Rules benchmark CLI."""

    return run_rules_benchmark()


if __name__ == "__main__":
    raise SystemExit(main())
