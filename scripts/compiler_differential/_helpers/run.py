"""Build run options and compare a corpus project by project."""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.compiler_differential._helpers.corpus import build_corpus
from scripts.compiler_differential._helpers.options import parse_engine_environment
from scripts.compiler_differential._helpers.project_comparison import compare_project
from scripts.compiler_differential._helpers.report import format_comparison
from scripts.compiler_differential.models import (
    CorpusProject,
    DifferentialOptions,
    ProjectComparison,
)


def differential_options(*, args: argparse.Namespace, work_dir: Path) -> DifferentialOptions:
    """Return run options from parsed command-line arguments."""

    return DifferentialOptions(
        engines=(args.engines[0], args.engines[1]),
        work_dir=work_dir,
        jobs=args.jobs,
        stage_captures=args.stage_captures,
        python=args.python,
        engine_environment=parse_engine_environment(args.engine_env),
    )


def selected_corpus(*, args: argparse.Namespace, repo_root: Path) -> list[CorpusProject]:
    """Return the projects selected by the parsed command-line arguments."""

    return build_corpus(
        repo_root=repo_root,
        corpora=tuple(args.corpus),
        seeds=range(args.seed_start, args.seed_start + args.seeds),
        dense_models=args.dense_models,
        projects=tuple(path.absolute() for path in args.project),
        project_expectation=args.expect,
    )


def compare_corpus(
    *, corpus: list[CorpusProject], options: DifferentialOptions
) -> list[ProjectComparison]:
    """Compare every project, printing each result as it completes."""

    print(
        f"Comparing {len(corpus)} projects ({options.engines[0]} vs {options.engines[1]}, "
        f"{options.jobs} jobs) in {options.work_dir}",
        file=sys.stderr,
    )
    comparisons: list[ProjectComparison] = []
    with ThreadPoolExecutor(max_workers=options.jobs) as pool:
        for comparison in pool.map(
            lambda project: compare_project(project=project, options=options), corpus
        ):
            comparisons.append(comparison)
            print(format_comparison(comparison=comparison, engines=options.engines))
            sys.stdout.flush()
    return comparisons
