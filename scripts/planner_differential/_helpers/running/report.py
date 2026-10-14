"""Render planner differential results for terminals and CI logs."""

from __future__ import annotations

from scripts.planner_differential.constants import MODE_RECORD
from scripts.planner_differential.models import ProjectDifference, ProjectResult


def format_result(result: ProjectResult) -> str:
    """Render one project's verdict, harness error and every readable diff."""

    status: str = "ERROR" if result.error else ("DIFF " if result.differences else "OK   ")
    lines: list[str] = [f"{status} {result.project} ({result.seconds:.1f}s)"]
    if result.error:
        lines.extend(f"    {line}" for line in result.error.rstrip().splitlines())
    for difference in result.differences:
        lines.append(_format_difference(difference))
    return "\n".join(lines)


def format_summary(*, results: list[ProjectResult], mode: str, seconds: float) -> str:
    """Summarize the run; a difference or harness error reports FAILED."""

    failed: list[ProjectResult] = [
        result for result in results if result.differences or result.error
    ]
    if not failed:
        verb: str = "recorded" if mode == MODE_RECORD else "matched the baseline"
        return f"Planner differential passed: {len(results)} projects {verb} in {seconds:.1f}s"
    return (
        f"Planner differential FAILED: {len(failed)} of {len(results)} projects differ or "
        f"errored in {seconds:.1f}s"
    )


def _format_difference(difference: ProjectDifference) -> str:
    body: str = "\n".join(f"      {line}" for line in difference.diff.splitlines())
    return f"  - step {difference.step}: {difference.artifact}\n{body}"
