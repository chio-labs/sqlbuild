"""CLI entry for the dupscore duplication advisory tool (see scripts/dupscore/README.md)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from scripts.dupscore._helpers.clones.rendering import render_clone_json, render_clone_text
from scripts.dupscore._helpers.inputs.cli import clone_options_from, parse_arguments
from scripts.dupscore._helpers.inputs.config import load_config
from scripts.dupscore._helpers.package_pairs.fusion import filter_report_to_domain
from scripts.dupscore._helpers.package_pairs.rendering import (
    render_delta_json,
    render_delta_text,
    render_pair_json,
    render_pair_text,
    render_report_json,
    render_report_text,
)
from scripts.dupscore.constants import (
    CLONES_MODE,
    CONFIG_FILENAME,
    DEFAULT_CLONE_TOP_RESULTS,
    DEFAULT_TOP_RESULTS,
    PAIR_ARGUMENT_COUNT,
    PAIR_MODE,
)
from scripts.dupscore.exceptions import DupscoreUsageError
from scripts.dupscore.main.build_clone_report import build_clone_report
from scripts.dupscore.main.build_pair_evidence import build_pair_evidence
from scripts.dupscore.main.build_report import build_report
from scripts.dupscore.main.build_report_delta import build_report_delta
from scripts.dupscore.models import (
    CloneReport,
    DupscoreConfig,
    DupscoreReport,
    PairEvidenceReport,
    ReportDelta,
)


def dupscore(argv: list[str] | None = None) -> int:
    """Run the dupscore CLI and print the requested advisory output."""

    args: argparse.Namespace = parse_arguments(argv)
    config_path: Path = Path(__file__).resolve().parents[1] / CONFIG_FILENAME
    config: DupscoreConfig = load_config(config_path)
    repo_root: Path = (
        args.repo_root.resolve()
        if args.repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    output: str = (
        _execute_clones(args=args, config=config, repo_root=repo_root)
        if args.mode == CLONES_MODE
        else _execute(args=args, config=config, repo_root=repo_root)
    )
    print(output)
    return 0


def _execute(*, args: argparse.Namespace, config: DupscoreConfig, repo_root: Path) -> str:
    top: int = args.top if args.top is not None else DEFAULT_TOP_RESULTS
    current: DupscoreReport = build_report(repo_root=repo_root, revision=None, config=config)
    if args.mode == PAIR_MODE:
        if len(args.packages) != PAIR_ARGUMENT_COUNT:
            raise DupscoreUsageError("pair mode requires exactly two package names")
        evidence: PairEvidenceReport = build_pair_evidence(
            report=current,
            left=args.packages[0],
            right=args.packages[1],
        )
        return render_pair_json(evidence) if args.as_json else render_pair_text(evidence)
    if args.since is not None:
        base: DupscoreReport = build_report(repo_root=repo_root, revision=args.since, config=config)
        delta: ReportDelta = build_report_delta(base=base, current=current, top=top)
        return render_delta_json(delta) if args.as_json else render_delta_text(delta)
    filtered: DupscoreReport = filter_report_to_domain(report=current, domain=args.domain)
    return (
        render_report_json(report=filtered, top=top)
        if args.as_json
        else render_report_text(report=filtered, top=top)
    )


def _execute_clones(*, args: argparse.Namespace, config: DupscoreConfig, repo_root: Path) -> str:
    top: int = args.top if args.top is not None else DEFAULT_CLONE_TOP_RESULTS
    print(f"dupscore: detecting function clones in {repo_root} ...", file=sys.stderr)
    started: float = time.perf_counter()
    try:
        report: CloneReport = build_clone_report(
            repo_root=repo_root, options=clone_options_from(args), config=config
        )
    except Exception:
        print("dupscore: clone detection failed", file=sys.stderr)
        raise
    unit_total: int = sum(report.unit_counts.values())
    print(
        f"dupscore: found {len(report.clusters)} clone clusters across {unit_total} units "
        f"in {time.perf_counter() - started:.1f}s",
        file=sys.stderr,
    )
    if args.as_json:
        return render_clone_json(report=report, top=top)
    return render_clone_text(report=report, top=top)
