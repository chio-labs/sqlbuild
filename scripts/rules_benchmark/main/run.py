"""Rules benchmark command entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.rules_benchmark._helpers.workflow import run_benchmark


def run_rules_benchmark(argv: list[str] | None = None) -> int:
    """Parse benchmark arguments and run all required scenarios."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--models", type=int, choices=(1000, 3000, 5000, 10000), required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--output", type=Path)
    arguments: argparse.Namespace = parser.parse_args(argv)
    if arguments.iterations < 1:
        parser.error("--iterations must be positive")
    return run_benchmark(
        model_count=arguments.models,
        iterations=arguments.iterations,
        output=arguments.output,
    )
