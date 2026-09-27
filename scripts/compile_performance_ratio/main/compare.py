"""Fail when head compiles slower than base by more than a ratio on the same runner."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from scripts.compile_performance_ratio._helpers.measure import (
    compare_builds,
    write_benchmark_project,
)
from scripts.compile_performance_ratio._helpers.report import append_summary, comparison_markdown
from scripts.compile_performance_ratio.constants import (
    DEFAULT_MAX_RATIO,
    DEFAULT_RUNS,
    PROJECT_KINDS,
)
from scripts.compile_performance_ratio.models import CompileComparison


def compare_compile_performance(argv: list[str] | None = None) -> int:
    """Compare base and head cold compiles and enforce the wall and CPU ratio limit."""

    args: argparse.Namespace = _parse_args(argv)
    summary_value: str | None = os.environ.get("GITHUB_STEP_SUMMARY")
    with tempfile.TemporaryDirectory(prefix="sqlbuild-ratio-") as root:
        project_dir: Path = Path(root) / f"{args.kind}_{args.models}"
        print(f"Generating {args.kind} project with {args.models} models", file=sys.stderr)
        write_benchmark_project(kind=args.kind, project_dir=project_dir, models=args.models)
        print(f"Comparing base and head over {args.runs} alternating runs", file=sys.stderr)
        comparison: CompileComparison = compare_builds(
            kind=args.kind,
            models=args.models,
            project_dir=project_dir,
            base_python=args.base_python,
            head_python=args.head_python,
            runs=args.runs,
        )
    markdown: str = comparison_markdown(
        comparison=comparison, runs=args.runs, max_ratio=args.max_ratio
    )
    print(markdown)
    append_summary(path=Path(summary_value) if summary_value else None, markdown=markdown)
    exceeded: list[str] = [
        f"{name} ratio {ratio:.3f} exceeds {args.max_ratio:.2f}"
        for name, ratio in (("wall", comparison.wall_ratio), ("CPU", comparison.cpu_ratio))
        if ratio > args.max_ratio
    ]
    if exceeded:
        print("Compile performance regression: " + "; ".join(exceeded), file=sys.stderr)
        return 1
    print("Compile performance within the same-runner limit", file=sys.stderr)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Compare base and head cold compiles on the same machine."
    )
    parser.add_argument("--kind", choices=PROJECT_KINDS, required=True)
    parser.add_argument("--models", type=int, required=True)
    parser.add_argument("--base-python", type=Path, required=True)
    parser.add_argument("--head-python", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--max-ratio", type=float, default=DEFAULT_MAX_RATIO)
    return parser.parse_args(argv)
