"""Render same-runner comparison results for logs and job summaries."""

from __future__ import annotations

import platform
from pathlib import Path

from scripts.compile_performance_ratio.constants import REPORTED_PHASES
from scripts.compile_performance_ratio.models import CompileComparison


def comparison_markdown(
    *, comparison: CompileComparison, runs: int, max_ratio: float, per_side_projects: bool
) -> str:
    """Summarize medians, ratios and per-phase timings as a Markdown table."""

    generation: str = (
        "Projects generated per side: base with the base checkout's generator, head with head's."
        if per_side_projects
        else "One project generated with head's generator and compiled by both builds."
    )
    lines: list[str] = [
        f"### {comparison.kind} {comparison.models} models: head vs base (same runner)",
        "",
        f"Runner CPU: {cpu_model()}; {runs} alternating runs each; limit {max_ratio:.2f}x.",
        "",
        generation,
        "",
        "| Metric | Base | Head | Ratio |",
        "|---|---:|---:|---:|",
        f"| Wall (s) | {comparison.base_wall_seconds:.2f} | "
        f"{comparison.head_wall_seconds:.2f} | {comparison.wall_ratio:.3f} |",
        f"| CPU (s) | {comparison.base_cpu_seconds:.2f} | "
        f"{comparison.head_cpu_seconds:.2f} | {comparison.cpu_ratio:.3f} |",
    ]
    for phase in REPORTED_PHASES:
        base: float = comparison.base_timings_ms.get(phase, 0)
        head: float = comparison.head_timings_ms.get(phase, 0)
        ratio: str = f"{head / base:.3f}" if base else "n/a"
        lines.append(f"| {phase} | {base:.0f} | {head:.0f} | {ratio} |")
    return "\n".join(lines) + "\n"


def append_summary(*, path: Path | None, markdown: str) -> None:
    """Append to the CI job summary when one is configured."""

    if path is None:
        return
    with path.open("a", encoding="utf-8") as summary:
        summary.write(markdown + "\n")


def cpu_model() -> str:
    """Return the runner CPU model name."""

    cpuinfo: Path = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"
