"""Required-CI Rules performance benchmark command."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.rules_benchmark._helpers.workflow import run_ci_benchmark


def main() -> int:
    """Run the bounded CI benchmark and write machine and human evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--max-seconds", type=int, default=420)
    arguments = parser.parse_args()
    if arguments.max_seconds < 1:
        parser.error("--max-seconds must be positive")
    return run_ci_benchmark(
        output=arguments.output,
        summary_output=arguments.summary_output,
        max_seconds=arguments.max_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
