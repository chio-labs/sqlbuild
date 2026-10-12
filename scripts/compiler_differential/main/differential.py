"""Run sqb compile and plan across a project corpus and check outputs against goldens."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

from scripts.compiler_differential._helpers.coverage.analysis import required_analysis_kinds
from scripts.compiler_differential._helpers.coverage.discovery import required_discovery_kinds
from scripts.compiler_differential._helpers.coverage.render import required_render_kinds
from scripts.compiler_differential._helpers.goldens.goldens import write_golden_seed_range
from scripts.compiler_differential._helpers.running.options import parse_expected_outcome
from scripts.compiler_differential._helpers.running.report import (
    format_analysis_coverage,
    format_discovery_coverage,
    format_render_coverage,
    format_summary,
)
from scripts.compiler_differential._helpers.running.run import (
    compare_corpus,
    differential_options,
    selected_corpus,
)
from scripts.compiler_differential.constants import (
    CORPUS_NAMES,
    CORPUS_SEEDS,
    DEFAULT_DENSE_MODELS,
    DEFAULT_SEED_COUNT,
    EXPECT_SUCCESS,
    GOLDEN_DIRECTORY,
    GOLDEN_MODE_UPDATE,
    GOLDEN_MODES,
    PER_PULL_REQUEST_CORPORA,
)
from scripts.compiler_differential.models import DifferentialOptions, ProjectComparison


def run_compiler_differential(argv: list[str] | None = None) -> int:
    """Run the selected corpus; exit 1 when any project misses its expectation or golden."""

    args: argparse.Namespace = _parse_args(argv)
    repo_root: Path = Path(__file__).resolve().parents[3]
    started: float = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="sqlbuild-differential-") as temporary:
        work_dir: Path = (args.work_dir or Path(temporary)).absolute()
        options: DifferentialOptions = differential_options(args=args, work_dir=work_dir)
        comparisons: list[ProjectComparison] = compare_corpus(
            corpus=selected_corpus(args=args, repo_root=repo_root), options=options
        )
    missing_coverage: dict[str, tuple[str, ...]] = (
        _seed_coverage(comparisons=comparisons, options=options)
        if options.stage_captures and CORPUS_SEEDS in args.corpus
        else {}
    )
    if args.goldens == GOLDEN_MODE_UPDATE and CORPUS_SEEDS in args.corpus:
        write_golden_seed_range(
            golden_dir=args.golden_dir, seed_start=args.seed_start, seeds=args.seeds
        )
    print(
        format_summary(
            comparisons=comparisons,
            seconds=time.monotonic() - started,
            missing_coverage=missing_coverage,
        )
    )
    return (
        1
        if any(missing_coverage.values())
        or any(comparison.differences for comparison in comparisons)
        else 0
    )


def _seed_coverage(
    *, comparisons: list[ProjectComparison], options: DifferentialOptions
) -> dict[str, tuple[str, ...]]:
    """Print each stage's coverage; return the missing kinds each requirement enforces."""

    discovered: frozenset[str] = frozenset().union(
        *(comparison.discovered_kinds for comparison in comparisons)
    )
    rendered: frozenset[str] = frozenset().union(
        *(comparison.rendered_kinds for comparison in comparisons)
    )
    required_discovery: tuple[str, ...] = required_discovery_kinds()
    analysed: frozenset[str] = frozenset().union(
        *(comparison.analysed_kinds for comparison in comparisons)
    )
    required_render: tuple[str, ...] = required_render_kinds()
    required_analysis: tuple[str, ...] = required_analysis_kinds()
    print(format_discovery_coverage(covered=discovered, required=required_discovery))
    print(format_render_coverage(covered=rendered, required=required_render))
    print(format_analysis_coverage(covered=analysed, required=required_analysis))
    missing: dict[str, tuple[str, ...]] = {}
    if options.require_discovery_coverage:
        missing["discovery"] = tuple(kind for kind in required_discovery if kind not in discovered)
    if options.require_render_coverage:
        missing["render"] = tuple(kind for kind in required_render if kind not in rendered)
    if options.require_analysis_coverage:
        missing["analysis"] = tuple(kind for kind in required_analysis if kind not in analysed)
    return missing


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.run_compiler_differential",
        description="Check sqb compile and plan output against golden files.",
    )
    parser.add_argument(
        "--corpus",
        nargs="*",
        choices=CORPUS_NAMES,
        default=list(PER_PULL_REQUEST_CORPORA),
        help="corpora to check (default: the per-PR corpora; pass none with --project)",
    )
    parser.add_argument("--project", nargs="*", type=Path, default=[], help="extra project dirs")
    parser.add_argument(
        "--expect",
        type=parse_expected_outcome,
        default=EXPECT_SUCCESS,
        metavar="success|failure:CODE",
        help="outcome every --project must produce (default: success)",
    )
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEED_COUNT)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--dense-models", type=int, default=DEFAULT_DENSE_MODELS)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--stage-captures",
        action="store_true",
        help="also dump every frontier object, for the coverage requirements",
    )
    parser.add_argument(
        "--require-discovery-coverage",
        action="store_true",
        help="fail unless the seed corpus exercises every discovery input kind (needs captures)",
    )
    parser.add_argument(
        "--require-render-coverage",
        action="store_true",
        help="fail unless the seed corpus exercises every render input kind (needs captures)",
    )
    parser.add_argument(
        "--require-analysis-coverage",
        action="store_true",
        help="fail unless the seed corpus exercises every analysis input kind (needs captures)",
    )
    parser.add_argument(
        "--goldens",
        choices=GOLDEN_MODES,
        default=None,
        help=(
            "check fixture, example, seed and failure outputs against the golden files, or "
            "rewrite them from this run"
        ),
    )
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=None,
        help=f"golden output directory (default: {GOLDEN_DIRECTORY} in the repository)",
    )
    parser.add_argument("--work-dir", type=Path, default=None, help="keep run directories here")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="copy each failing project's target/, stderr and compiled-test stats to PATH",
    )
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args: argparse.Namespace = parser.parse_args(argv)
    repo_root: Path = Path(__file__).resolve().parents[3]
    if args.golden_dir is None:
        args.golden_dir = repo_root / GOLDEN_DIRECTORY
    for flag, required in (
        ("--require-discovery-coverage", args.require_discovery_coverage),
        ("--require-render-coverage", args.require_render_coverage),
        ("--require-analysis-coverage", args.require_analysis_coverage),
    ):
        if required and not (args.stage_captures and CORPUS_SEEDS in args.corpus):
            parser.error(f"{flag} needs --stage-captures and the seeds corpus")
    return args
