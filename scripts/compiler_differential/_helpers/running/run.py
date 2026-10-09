"""Build run options and compare a corpus project by project."""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.project_comparison import compare_project
from scripts.compiler_differential._helpers.corpus.corpus import build_corpus
from scripts.compiler_differential._helpers.running.options import parse_engine_environment
from scripts.compiler_differential._helpers.running.report import format_comparison
from scripts.compiler_differential.models import (
    CorpusProject,
    DifferentialOptions,
    FallbackGateRequest,
    ProjectComparison,
    RecordedRun,
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
        require_discovery_coverage=args.require_discovery_coverage,
        require_render_coverage=args.require_render_coverage,
        require_analysis_coverage=args.require_analysis_coverage,
        analysis_records=args.wheel_site_report is not None or args.native_fallbacks is not None,
        evidence_dir=args.evidence_dir,
        golden_mode=args.goldens,
        golden_dir=args.golden_dir,
    )


def fallback_gate_request(
    *, args: argparse.Namespace, engines: tuple[str, str]
) -> FallbackGateRequest | None:
    """Return the run's fallback allow-list gate, or None when it is off."""

    if args.native_fallbacks is None:
        return None
    return FallbackGateRequest(
        mode=args.native_fallbacks,
        allow_list=args.native_fallback_list,
        run=RecordedRun(
            engines=engines,
            corpora=tuple(args.corpus),
            seed_start=args.seed_start,
            seeds=args.seeds,
        ),
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
