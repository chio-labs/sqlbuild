"""Render differential results for terminals and CI logs."""

from __future__ import annotations

from scripts.compiler_differential.models import Difference, ProjectComparison


def format_comparison(*, comparison: ProjectComparison, engines: tuple[str, str]) -> str:
    """Render one project's verdict and the first difference in every differing artifact."""

    status: str = "OK  " if not comparison.differences else "DIFF"
    lines: list[str] = [f"{status} {comparison.project} ({comparison.seconds:.1f}s)"]
    for difference in comparison.differences:
        left_label, right_label = difference.labels or engines
        width: int = max(len(left_label), len(right_label))
        lines.append(f"  - {difference.artifact} at {difference.location}")
        lines.append(f"      {left_label:<{width}}: {difference.left}")
        lines.append(f"      {right_label:<{width}}: {difference.right}")
    return "\n".join(lines)


def format_summary(
    *, comparisons: list[ProjectComparison], engines: tuple[str, str], seconds: float
) -> str:
    """Summarize the run, naming the first difference of the first differing project."""

    differing: list[ProjectComparison] = [item for item in comparisons if item.differences]
    left_engine, right_engine = engines
    if not differing:
        return (
            f"Compiler differential passed: {len(comparisons)} projects identical "
            f"({left_engine} vs {right_engine}) in {seconds:.1f}s"
        )
    first: Difference = differing[0].differences[0]
    return (
        f"Compiler differential FAILED: {len(differing)} of {len(comparisons)} projects differ "
        f"({left_engine} vs {right_engine}) in {seconds:.1f}s\n"
        f"First difference: {first.project}: {first.artifact} at {first.location}"
    )
