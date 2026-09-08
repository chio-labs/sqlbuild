"""Reproducible local Project Policy benchmark command."""

from scripts.project_policy_benchmark.main.run import run_project_policy_benchmark


def main() -> int:
    """Run the Project Policy benchmark CLI."""

    return run_project_policy_benchmark()


if __name__ == "__main__":
    raise SystemExit(main())
