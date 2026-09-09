"""Rules benchmark command entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.rules_benchmark._helpers.workflow import run_benchmark, run_rule_count_benchmark


def run_rules_benchmark(argv: list[str] | None = None) -> int:
    """Parse benchmark arguments and run all required scenarios."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--models", type=int, choices=(1000, 3000, 5000, 10000), required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--rule-counts",
        type=int,
        nargs="+",
        help="Run the custom-rule count scaling profile for the supplied counts",
    )
    arguments: argparse.Namespace = parser.parse_args(argv)
    if arguments.iterations < 1:
        parser.error("--iterations must be positive")
    if arguments.rule_counts is not None:
        rule_counts: tuple[int, ...] = tuple(dict.fromkeys(arguments.rule_counts))
        if any(count < 3 or count > 999 for count in rule_counts):
            parser.error("--rule-counts values must be between 3 and 999")
        return run_rule_count_benchmark(
            model_count=arguments.models,
            iterations=arguments.iterations,
            rule_counts=rule_counts,
            output=arguments.output,
        )
    return run_benchmark(
        model_count=arguments.models,
        iterations=arguments.iterations,
        output=arguments.output,
    )
