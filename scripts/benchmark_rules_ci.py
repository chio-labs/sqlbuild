"""Required-CI Rules performance benchmark command."""

from scripts.rules_benchmark.main.run_ci import run_rules_ci_benchmark


def main() -> int:
    """Run the bounded CI benchmark and write machine and human evidence."""

    return run_rules_ci_benchmark()


if __name__ == "__main__":
    raise SystemExit(main())
