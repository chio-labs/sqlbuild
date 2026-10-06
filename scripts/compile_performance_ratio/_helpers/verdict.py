"""Decide whether head compiled slower than base beyond the same-runner ratio limit."""

from __future__ import annotations

import math

from scripts.compile_performance_ratio.constants import NOISE_FLOOR_SECONDS
from scripts.compile_performance_ratio.models import CompileComparison


def ratio_failures(
    *, comparisons: tuple[CompileComparison, ...], modes: tuple[str, ...], max_ratio: float
) -> tuple[str, ...]:
    """Describe every requested mode that is unmeasured or slower beyond the ratio and floor."""

    measured: dict[str, CompileComparison] = {
        comparison.mode: comparison for comparison in comparisons
    }
    failures: list[str] = []
    for mode in modes:
        comparison: CompileComparison | None = measured.get(mode)
        if comparison is None:
            failures.append(f"{mode}: no measurement")
            continue
        prefix: str = f"{comparison.kind} {comparison.models} {mode}"
        for metric, base, head, ratio in (
            (
                "wall",
                comparison.base_wall_seconds,
                comparison.head_wall_seconds,
                comparison.wall_ratio,
            ),
            ("CPU", comparison.base_cpu_seconds, comparison.head_cpu_seconds, comparison.cpu_ratio),
        ):
            if not _measured(base) or not _measured(head):
                failures.append(
                    f"{prefix}: {metric} measurement missing (base {base:.2f} s, head {head:.2f} s)"
                )
            elif ratio > max_ratio and head - base > NOISE_FLOOR_SECONDS:
                failures.append(f"{prefix}: {metric} ratio {ratio:.3f} exceeds {max_ratio:.2f}")
    return tuple(failures)


def _measured(seconds: float) -> bool:
    return math.isfinite(seconds) and seconds > 0
