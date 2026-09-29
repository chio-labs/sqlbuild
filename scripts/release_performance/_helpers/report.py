"""Render a release performance comparison for logs and the CI job summary."""

from __future__ import annotations

from pathlib import Path

from scripts.release_performance._helpers.verdict import metric_verdicts, regression_messages
from scripts.release_performance.constants import (
    MAX_CPU_RATIO,
    MAX_RSS_RATIO,
    MAX_WALL_RATIO,
    MIN_CPU_REGRESSION_SECONDS,
    MIN_RSS_REGRESSION_BYTES,
    MIN_WALL_REGRESSION_SECONDS,
)
from scripts.release_performance.models import MetricVerdict, ReleaseComparison

_MIB: int = 1024 * 1024


def comparison_markdown(*, comparison: ReleaseComparison) -> str:
    """Summarize per-command medians, ratios and the overall verdict as Markdown."""

    lines: list[str] = [
        f"### Release performance: {comparison.candidate_version} (candidate) vs "
        f"{comparison.baseline_version} (baseline)",
        "",
        f"Same runner: {comparison.runner.cpu_model}, {comparison.runner.cpu_count} CPUs; "
        f"load average {_load(comparison.runner.load_average_before)} before and "
        f"{_load(comparison.runner.load_average_after)} after. "
        f"{comparison.runs} interleaved runs per version; medians shown.",
        "",
        f"Limits: wall {_percent(MAX_WALL_RATIO)} (ignored under "
        f"{MIN_WALL_REGRESSION_SECONDS:g} s), CPU {_percent(MAX_CPU_RATIO)} (ignored under "
        f"{MIN_CPU_REGRESSION_SECONDS:g} s), peak RSS {_percent(MAX_RSS_RATIO)} (ignored under "
        f"{MIN_RSS_REGRESSION_BYTES // _MIB} MiB).",
        "",
        "| Command | Wall (s) | Wall ratio | CPU (s) | CPU ratio | Peak RSS (MiB) | RSS ratio "
        "| Result |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for command in comparison.commands:
        wall, cpu, rss = metric_verdicts(comparison=command)
        regressed: bool = wall.regressed or cpu.regressed or rss.regressed
        lines.append(
            f"| `{command.name}` "
            f"| {wall.baseline:.2f} → {wall.candidate:.2f} | {_ratio(wall)} "
            f"| {cpu.baseline:.2f} → {cpu.candidate:.2f} | {_ratio(cpu)} "
            f"| {rss.baseline / _MIB:.0f} → {rss.candidate / _MIB:.0f} | {_ratio(rss)} "
            f"| {'❌ regressed' if regressed else '✅ ok'} |"
        )
    for skipped in comparison.skipped:
        lines.append(f"| `{skipped.name}` | – | – | – | – | – | – | ⚠️ skipped: {skipped.reason} |")
    lines.append("")
    failures: tuple[str, ...] = regression_messages(commands=comparison.commands)
    if failures:
        lines.append("**Result: failed.** " + "; ".join(failures) + ".")
    else:
        lines.append("**Result: passed.** No command exceeded the release limits.")
    if comparison.skipped:
        lines.append("")
        lines.append(
            f"**{len(comparison.skipped)} command(s) skipped** because a compared version "
            "predates them; they were not measured."
        )
    return "\n".join(lines) + "\n"


def error_markdown(*, message: str) -> str:
    """Report a comparison that could not complete."""

    return f"### Release performance\n\n**Result: error.** {message}\n"


def append_summary(*, path: Path | None, markdown: str) -> None:
    """Append to the CI job summary when one is configured."""

    if path is None:
        return
    with path.open("a", encoding="utf-8") as summary:
        _ = summary.write(markdown + "\n")


def _ratio(verdict: MetricVerdict) -> str:
    text: str = f"{verdict.ratio:.3f}x"
    return f"**{text}**" if verdict.regressed else text


def _percent(ratio: float) -> str:
    return f"+{round((ratio - 1) * 100)}%"


def _load(values: tuple[float, float, float]) -> str:
    return "/".join(f"{value:.2f}" for value in values)
