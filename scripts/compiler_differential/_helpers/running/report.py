"""Render differential results for terminals and CI logs."""

from __future__ import annotations

from scripts.compiler_differential.constants import CONFIG_ONLY_KINDS
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
    *,
    comparisons: list[ProjectComparison],
    engines: tuple[str, str],
    seconds: float,
    missing_coverage: tuple[str, ...] = (),
) -> str:
    """Summarize the run; any difference or required-but-missing coverage reports FAILED."""

    differing: list[ProjectComparison] = [item for item in comparisons if item.differences]
    left_engine, right_engine = engines
    if not differing and not missing_coverage:
        return (
            f"Compiler differential passed: {len(comparisons)} projects identical "
            f"({left_engine} vs {right_engine}) in {seconds:.1f}s"
        )
    lines: list[str] = [
        f"Compiler differential FAILED: {len(differing)} of {len(comparisons)} projects differ "
        f"({left_engine} vs {right_engine}) in {seconds:.1f}s"
    ]
    if differing:
        first: Difference = differing[0].differences[0]
        lines.append(f"First difference: {first.project}: {first.artifact} at {first.location}")
    if missing_coverage:
        lines.append(f"Required discovery coverage missing: {', '.join(missing_coverage)}")
    return "\n".join(lines)


def format_discovery_coverage(*, covered: frozenset[str], required: tuple[str, ...]) -> str:
    """Report how many required discovery input kinds the seed corpus exercised."""

    missing: list[str] = [kind for kind in required if kind not in covered]
    line: str = (
        f"Discovery coverage: {len(required) - len(missing)} of {len(required)} input kinds "
        "exercised by the seed corpus"
    )
    config_only: str = "; ".join(
        f"{kind} (only proves {meaning})" for kind, meaning in CONFIG_ONLY_KINDS.items()
    )
    line = f"{line}\n  config-only kinds: {config_only}"
    return line if not missing else f"{line}\n  missing: {', '.join(missing)}"
