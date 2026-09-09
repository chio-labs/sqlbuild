"""Required-CI Rules performance command."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.rules_benchmark._helpers.workflow import run_ci_benchmark
from scripts.rules_benchmark.constants import CI_DEFAULT_MAX_SECONDS


def run_rules_ci_benchmark(argv: list[str] | None = None) -> int:
    """Parse CI benchmark arguments and run the bounded profile."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--max-seconds", type=int, default=CI_DEFAULT_MAX_SECONDS)
    arguments: argparse.Namespace = parser.parse_args(argv)
    if arguments.max_seconds < 1:
        parser.error("--max-seconds must be positive")
    return run_ci_benchmark(
        output=arguments.output,
        summary_output=arguments.summary_output,
        max_seconds=arguments.max_seconds,
    )
