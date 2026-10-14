"""Parse the planner differential command line into run options."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.planner_differential.constants import (
    ACTUAL_SUFFIX,
    DEFAULT_BASELINE_DIR,
    DEFAULT_JOBS,
    DEFAULT_SEED_COUNT,
    MODE_CHECK,
    MODES,
    STEPS,
)
from scripts.planner_differential.models import RunOptions


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse and validate the harness arguments."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.run_planner_differential",
        description=(
            "Build each corpus project, apply a fixed mutation script, and record or check "
            "plans, plan outputs and state-table rows after every step."
        ),
    )
    parser.add_argument("mode", choices=MODES, help="record a baseline, or check against it")
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path(DEFAULT_BASELINE_DIR),
        help=(
            f"baseline directory (default: {DEFAULT_BASELINE_DIR}); check writes the run "
            f"beside it with an {ACTUAL_SUFFIX} suffix"
        ),
    )
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEED_COUNT)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument(
        "--projects",
        nargs="*",
        default=[],
        help="keep projects whose name contains any of these, such as fixture/ or seed/3",
    )
    parser.add_argument(
        "--steps",
        nargs="*",
        choices=[step.name for step in STEPS],
        default=[],
        help="run only these steps of the mutation script, in script order",
    )
    parser.add_argument("--limit", type=int, default=None, help="run only the first N projects")
    parser.add_argument(
        "--work-dir", type=Path, default=None, help="keep project copies and captures here"
    )
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args: argparse.Namespace = parser.parse_args(argv)
    if args.mode == MODE_CHECK and not args.baseline_dir.is_dir():
        parser.error(f"no baseline at {args.baseline_dir}; run with `record` first")
    return args


def run_options(*, args: argparse.Namespace, work_dir: Path) -> RunOptions:
    """Return run options from parsed arguments, running in `work_dir`."""

    return RunOptions(
        work_dir=work_dir.absolute(),
        jobs=args.jobs,
        python=args.python,
        mode=args.mode,
        baseline_dir=args.baseline_dir.absolute(),
        keep_work=args.work_dir is not None,
        steps=tuple(step for step in STEPS if not args.steps or step.name in args.steps),
    )
