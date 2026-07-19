"""CLI entry for the dupscore duplication-risk advisory report."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.dupscore._helpers.config import load_config
from scripts.dupscore._helpers.fusion import filter_report_to_domain
from scripts.dupscore._helpers.rendering import (
    render_delta_json,
    render_delta_text,
    render_pair_json,
    render_pair_text,
    render_report_json,
    render_report_text,
)
from scripts.dupscore.constants import (
    CONFIG_FILENAME,
    DEFAULT_TOP_RESULTS,
    PAIR_ARGUMENT_COUNT,
    PAIR_MODE,
    REPORT_MODE,
)
from scripts.dupscore.exceptions import DupscoreUsageError
from scripts.dupscore.main.build_pair_evidence import build_pair_evidence
from scripts.dupscore.main.build_report import build_report
from scripts.dupscore.main.build_report_delta import build_report_delta
from scripts.dupscore.models import (
    DupscoreConfig,
    DupscoreReport,
    PairEvidenceReport,
    ReportDelta,
)


def dupscore(argv: list[str] | None = None) -> int:
    """Run the dupscore CLI and print the requested advisory output."""

    parser: argparse.ArgumentParser = _build_parser()
    args: argparse.Namespace = parser.parse_args(argv)
    config_path: Path = Path(__file__).resolve().parents[1] / CONFIG_FILENAME
    config: DupscoreConfig = load_config(config_path)
    output: str = _execute(args=args, config=config)
    print(output)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="dupscore")
    parser.add_argument("mode", nargs="?", choices=[REPORT_MODE, PAIR_MODE], default=REPORT_MODE)
    parser.add_argument("packages", nargs="*", default=[])
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_RESULTS)
    parser.add_argument("--domain", type=str, default=None)
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _execute(*, args: argparse.Namespace, config: DupscoreConfig) -> str:
    repo_root: Path = Path(__file__).resolve().parents[3]
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
        delta: ReportDelta = build_report_delta(base=base, current=current, top=args.top)
        return render_delta_json(delta) if args.as_json else render_delta_text(delta)
    filtered: DupscoreReport = filter_report_to_domain(report=current, domain=args.domain)
    return (
        render_report_json(report=filtered, top=args.top)
        if args.as_json
        else render_report_text(report=filtered, top=args.top)
    )
