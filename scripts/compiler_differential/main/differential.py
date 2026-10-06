"""Compare compile and plan output of two compiler engines across a project corpus."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

from scripts.compiler_differential._helpers.options import parse_expected_outcome
from scripts.compiler_differential._helpers.report import format_summary
from scripts.compiler_differential._helpers.run import (
    compare_corpus,
    differential_options,
    selected_corpus,
)
from scripts.compiler_differential.constants import (
    CORPUS_NAMES,
    DEFAULT_DENSE_MODELS,
    DEFAULT_ENGINES,
    DEFAULT_SEED_COUNT,
    EXPECT_SUCCESS,
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
    print(
        format_summary(
            comparisons=comparisons,
            engines=options.engines,
            seconds=time.monotonic() - started,
        )
    )
    return 1 if any(comparison.differences for comparison in comparisons) else 0


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
    parser.add_argument("--engines", nargs=2, default=list(DEFAULT_ENGINES), metavar="ENGINE")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--stage-captures",
        action="store_true",
        help="also dump and diff every frontier object to localise a mismatch to a stage",
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
    return parser.parse_args(argv)
