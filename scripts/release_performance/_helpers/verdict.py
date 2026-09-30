"""Decide whether the candidate regressed against the baseline beyond the release limits."""

from __future__ import annotations

import statistics

from scripts.release_performance.constants import (
    MAX_CPU_RATIO,
    MAX_RSS_RATIO,
    MAX_WALL_RATIO,
    MIN_CPU_REGRESSION_SECONDS,
    MIN_RSS_REGRESSION_BYTES,
    MIN_WALL_REGRESSION_SECONDS,
)
from scripts.release_performance.models import (
    BenchmarkCommand,
    CommandComparison,
    CommandSample,
    MetricVerdict,
)


def metric_verdicts(*, comparison: CommandComparison) -> tuple[MetricVerdict, ...]:
    """Compare median wall and CPU time and worst-run peak RSS of one command."""

    baseline: CommandSample = summary_sample(samples=comparison.baseline)
    candidate: CommandSample = summary_sample(samples=comparison.candidate)
    return (
        _verdict(
            command=comparison.name,
            metric="wall",
            baseline=baseline.wall_seconds,
            candidate=candidate.wall_seconds,
            max_ratio=MAX_WALL_RATIO,
            floor=MIN_WALL_REGRESSION_SECONDS,
        ),
        _verdict(
            command=comparison.name,
            metric="CPU",
            baseline=baseline.cpu_seconds,
            candidate=candidate.cpu_seconds,
            max_ratio=MAX_CPU_RATIO,
            floor=MIN_CPU_REGRESSION_SECONDS,
        ),
        _verdict(
            command=comparison.name,
            metric="peak RSS",
            baseline=float(baseline.peak_rss_bytes),
            candidate=float(candidate.peak_rss_bytes),
            max_ratio=MAX_RSS_RATIO,
            floor=float(MIN_RSS_REGRESSION_BYTES),
        ),
    )


def regression_messages(*, commands: tuple[CommandComparison, ...]) -> tuple[str, ...]:
    """Describe every metric that exceeds both its ratio limit and its absolute floor."""

    return tuple(
        f"{verdict.command}: {verdict.metric} {verdict.ratio:.3f}x exceeds {verdict.max_ratio:.2f}x"
        for verdict in all_verdicts(commands=commands)
        if verdict.regressed
    )


def all_verdicts(*, commands: tuple[CommandComparison, ...]) -> tuple[MetricVerdict, ...]:
    """Return the metric verdicts of every measured command in order."""

    verdicts: list[MetricVerdict] = []
    for comparison in commands:
        verdicts.extend(metric_verdicts(comparison=comparison))
    return tuple(verdicts)


def summary_sample(*, samples: tuple[CommandSample, ...]) -> CommandSample:
    """Return median wall and CPU time and the worst peak RSS of samples.

    Peak RSS depends on whether concurrent phases overlap, so it lands on one of a few levels
    run to run; the worst run is stable where a median flips between levels.
    """

    return CommandSample(
        wall_seconds=statistics.median(sample.wall_seconds for sample in samples),
        cpu_seconds=statistics.median(sample.cpu_seconds for sample in samples),
        peak_rss_bytes=max(sample.peak_rss_bytes for sample in samples),
    )


def skip_reason(
    *, command: BenchmarkCommand, baseline_version: str, candidate_version: str
) -> str | None:
    """Explain why a command cannot run on a compared version, or return None when it can."""

    if command.minimum_version is None:
        return None
    minimum: tuple[int, ...] = version_key(version=command.minimum_version)
    for label, version in (("baseline", baseline_version), ("candidate", candidate_version)):
        if version_key(version=version) < minimum:
            return f"requires sqlbuild {command.minimum_version} or later; {label} is {version}"
    return None


def version_key(*, version: str) -> tuple[int, ...]:
    """Order plain X.Y.Z release versions numerically."""

    return tuple(int(part) for part in version.split("."))


def _verdict(
    *,
    command: str,
    metric: str,
    baseline: float,
    candidate: float,
    max_ratio: float,
    floor: float,
) -> MetricVerdict:
    return MetricVerdict(
        command=command,
        metric=metric,
        baseline=baseline,
        candidate=candidate,
        max_ratio=max_ratio,
        floor=floor,
        regressed=candidate > baseline * max_ratio and candidate - baseline > floor,
    )
