"""Record or check plans, plan outputs and state rows across a fixed mutation script."""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from scripts.planner_differential._helpers.corpus.corpus import build_corpus, filter_corpus
from scripts.planner_differential._helpers.running.options import parse_args, run_options
from scripts.planner_differential._helpers.running.report import format_summary
from scripts.planner_differential._helpers.running.run import run_corpus
from scripts.planner_differential.models import PlannerProject, ProjectResult


def run_planner_differential(argv: list[str] | None = None) -> int:
    """Run the corpus; in check mode exit 1 when any project differs from its baseline."""

    args: argparse.Namespace = parse_args(argv)
    projects: list[PlannerProject] = filter_corpus(
        projects=build_corpus(
            repo_root=Path(__file__).resolve().parents[3],
            seed_start=args.seed_start,
            seeds=args.seeds,
        ),
        names=tuple(args.projects),
        limit=args.limit,
    )
    started: float = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="sqlbuild-planner-differential-") as temporary:
        results: list[ProjectResult] = run_corpus(
            projects=projects,
            options=run_options(args=args, work_dir=args.work_dir or Path(temporary)),
        )
    print(format_summary(results=results, mode=args.mode, seconds=time.monotonic() - started))
    return 1 if any(result.differences or result.error for result in results) else 0
