"""Compare compile and plan output of two compiler engines across a project corpus."""

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
from scripts.compiler_differential._helpers.running.native_fallbacks import native_fallback_gate
from scripts.compiler_differential._helpers.running.options import parse_expected_outcome
from scripts.compiler_differential._helpers.running.records import write_wheel_site_report
from scripts.compiler_differential._helpers.running.report import (
    format_analysis_coverage,
    format_discovery_coverage,
    format_render_coverage,
    format_summary,
)
from scripts.compiler_differential._helpers.running.run import (
    compare_corpus,
    differential_options,
    fallback_gate_request,
    selected_corpus,
)
from scripts.compiler_differential.constants import (
    CORPUS_NAMES,
    CORPUS_SEEDS,
    DEFAULT_DENSE_MODELS,
    DEFAULT_ENGINES,
    DEFAULT_SEED_COUNT,
    ENGINE_NAMES,
    EXPECT_SUCCESS,
    GOLDEN_DIRECTORY,
    GOLDEN_MODES,
    NATIVE_FALLBACK_LIST,
    NATIVE_FALLBACK_MODES,
    PER_PULL_REQUEST_CORPORA,
)
from scripts.compiler_differential.models import DifferentialOptions, ProjectComparison


def run_compiler_differential(argv: list[str] | None = None) -> int:
    """Run the selected corpus under both engines; exit 1 when any artifact differs."""

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
    if args.wheel_site_report is not None:
        write_wheel_site_report(
            path=args.wheel_site_report, comparisons=comparisons, engines=options.engines
        )
    fallback_failures: tuple[str, ...] = native_fallback_gate(
        request=fallback_gate_request(args=args, engines=options.engines),
        comparisons=comparisons,
    )
    print(
        format_summary(
            comparisons=comparisons,
            engines=options.engines,
            seconds=time.monotonic() - started,
            missing_coverage=missing_coverage,
            gate_failures=fallback_failures,
        )
    )
    return (
        1
        if any(missing_coverage.values())
        or fallback_failures
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
        description="Compare sqb compile and plan output between two compiler engines.",
    )
    parser.add_argument(
        "--corpus",
        nargs="*",
        choices=CORPUS_NAMES,
        default=list(PER_PULL_REQUEST_CORPORA),
        help="corpora to compare (default: the per-PR corpora; pass none with --project)",
    )
    parser.add_argument("--project", nargs="*", type=Path, default=[], help="extra project dirs")
    parser.add_argument(
        "--expect",
        type=parse_expected_outcome,
        default=EXPECT_SUCCESS,
        metavar="success|failure:CODE",
        help="outcome every --project must produce on the first engine (default: success)",
    )
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEED_COUNT)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--dense-models", type=int, default=DEFAULT_DENSE_MODELS)
    parser.add_argument(
        "--engines",
        nargs=2,
        choices=ENGINE_NAMES,
        default=list(DEFAULT_ENGINES),
        metavar="ENGINE",
        help=(
            "oracle and candidate engines (default: python native-preview, every native stage; "
            "pass python native to cover only the shipped native stages)"
        ),
    )
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--stage-captures",
        action="store_true",
        help="also dump and diff every frontier object to localise a mismatch to a stage",
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
        "--wheel-site-report",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "record Polyglot wheel calls by calling site and analysis deferrals in every engine "
            "process, print them and write them to PATH as JSON (reported, never gated)"
        ),
    )
    parser.add_argument(
        "--native-fallbacks",
        choices=NATIVE_FALLBACK_MODES,
        default=None,
        help=(
            "record native-to-Python fallbacks and analysis deferrals in every engine process and "
            "check them against the allow-list (new, changed or vanished entries fail), or "
            "rewrite the list from this run"
        ),
    )
    parser.add_argument(
        "--native-fallback-list",
        type=Path,
        default=None,
        help=f"fallback allow-list file (default: {NATIVE_FALLBACK_LIST} in the repository)",
    )
    parser.add_argument(
        "--goldens",
        choices=GOLDEN_MODES,
        default=None,
        help=(
            "check every engine's fixture, example, seed and failure outputs against the golden "
            "files, or rewrite them from the first (oracle) engine"
        ),
    )
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=None,
        help=f"golden output directory (default: {GOLDEN_DIRECTORY} in the repository)",
    )
    parser.add_argument(
        "--engine-env",
        action="append",
        default=[],
        metavar="ENGINE:NAME=VALUE",
        help="extra environment for one engine's processes",
    )
    parser.add_argument("--work-dir", type=Path, default=None, help="keep run directories here")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args: argparse.Namespace = parser.parse_args(argv)
    repo_root: Path = Path(__file__).resolve().parents[3]
    if args.golden_dir is None:
        args.golden_dir = repo_root / GOLDEN_DIRECTORY
    if args.native_fallback_list is None:
        args.native_fallback_list = repo_root / NATIVE_FALLBACK_LIST
    for flag, required in (
        ("--require-discovery-coverage", args.require_discovery_coverage),
        ("--require-render-coverage", args.require_render_coverage),
        ("--require-analysis-coverage", args.require_analysis_coverage),
    ):
        if required and not (args.stage_captures and CORPUS_SEEDS in args.corpus):
            parser.error(f"{flag} needs --stage-captures and the seeds corpus")
    return args
