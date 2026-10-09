"""Render differential results for terminals and CI logs."""

from __future__ import annotations

from scripts.compiler_differential.constants import (
    ANALYSIS_INDIRECT_KINDS,
    BASELINES_HINT,
    CONFIG_ONLY_KINDS,
    GOLDEN_LABEL,
    RENDER_CONFIG_ONLY_KINDS,
    RENDER_INDIRECT_KINDS,
)
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
    missing_coverage: dict[str, tuple[str, ...]] | None = None,
    gate_failures: tuple[str, ...] = (),
) -> str:
    """Summarize the run; a difference, missing coverage or gate failure reports FAILED."""

    differing: list[ProjectComparison] = [item for item in comparisons if item.differences]
    gaps: dict[str, tuple[str, ...]] = {
        stage: kinds for stage, kinds in (missing_coverage or {}).items() if kinds
    }
    left_engine, right_engine = engines
    if not differing and not gaps and not gate_failures:
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
    lines.extend(
        f"Required {stage} coverage missing: {', '.join(kinds)}" for stage, kinds in gaps.items()
    )
    if gate_failures:
        lines.append(f"Native fallback allow-list: {len(gate_failures)} problems (listed above)")
    if gate_failures or any(_golden_differs(comparison) for comparison in differing):
        lines.append(BASELINES_HINT)
    return "\n".join(lines)


def _golden_differs(comparison: ProjectComparison) -> bool:
    return any(GOLDEN_LABEL in (difference.labels or ()) for difference in comparison.differences)


def format_discovery_coverage(*, covered: frozenset[str], required: tuple[str, ...]) -> str:
    """Report how many required discovery input kinds the seed corpus exercised."""

    return _format_coverage(
        stage="Discovery",
        covered=covered,
        required=required,
        notes=(("config-only kinds", "only proves", CONFIG_ONLY_KINDS),),
    )


def format_render_coverage(*, covered: frozenset[str], required: tuple[str, ...]) -> str:
    """Report how many required render input kinds the seed corpus exercised."""

    return _format_coverage(
        stage="Render",
        covered=covered,
        required=required,
        notes=(
            ("config-only kinds", "only proves", RENDER_CONFIG_ONLY_KINDS),
            ("indirect kinds", "credited because", RENDER_INDIRECT_KINDS),
        ),
    )


def format_analysis_coverage(*, covered: frozenset[str], required: tuple[str, ...]) -> str:
    """Report how many required analysis input kinds the seed corpus exercised."""

    return _format_coverage(
        stage="Analysis",
        covered=covered,
        required=required,
        notes=(("indirect kinds", "credited because", ANALYSIS_INDIRECT_KINDS),),
    )


def _format_coverage(
    *,
    stage: str,
    covered: frozenset[str],
    required: tuple[str, ...],
    notes: tuple[tuple[str, str, dict[str, str]], ...],
) -> str:
    missing: list[str] = [kind for kind in required if kind not in covered]
    lines: list[str] = [
        f"{stage} coverage: {len(required) - len(missing)} of {len(required)} input kinds "
        "exercised by the seed corpus"
    ]
    for label, verb, kinds in notes:
        by_meaning: dict[str, list[str]] = {}
        for kind, meaning in kinds.items():
            by_meaning.setdefault(meaning, []).append(kind)
        described: str = "; ".join(
            f"{', '.join(names)} ({verb} {meaning})" for meaning, names in by_meaning.items()
        )
        lines.append(f"  {label}: {described or 'none'}")
    if missing:
        lines.append(f"  missing: {', '.join(missing)}")
    return "\n".join(lines)
