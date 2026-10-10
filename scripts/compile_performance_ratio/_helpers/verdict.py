"""Decide whether head compiled slower than base beyond the same-runner ratio limit."""

from __future__ import annotations

import math
from collections.abc import Mapping

from scripts.compile_performance_ratio.constants import CPU_METRIC
from scripts.compile_performance_ratio.models import CompileComparison


def ratio_failures(
    *,
    comparisons: tuple[CompileComparison, ...],
    modes: tuple[str, ...],
    max_ratio: float,
    noise_floor_seconds: float,
    mode_max_ratios: Mapping[str, float] | None = None,
    mode_cpu_max_ratios: Mapping[str, float] | None = None,
) -> tuple[str, ...]:
    """Describe every requested mode that is unmeasured or slower than ratio plus floor allow."""

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
        limit: float = (mode_max_ratios or {}).get(mode, max_ratio)
        for metric, base, head, ratio in (
            (
                "wall",
                comparison.base_wall_seconds,
                comparison.head_wall_seconds,
                comparison.wall_ratio,
            ),
            ("CPU", comparison.base_cpu_seconds, comparison.head_cpu_seconds, comparison.cpu_ratio),
        ):
            metric_limit: float = (
                (mode_cpu_max_ratios or {}).get(mode, limit) if metric == CPU_METRIC else limit
            )
            if not _measured(base) or not _measured(head):
                failures.append(
                    f"{prefix}: {metric} measurement missing (base {base:.2f} s, head {head:.2f} s)"
                )
            elif head > base * metric_limit + noise_floor_seconds:
                failures.append(f"{prefix}: {metric} ratio {ratio:.3f} exceeds {metric_limit:.2f}")
    return tuple(failures)


def phase_failures(
    *,
    comparisons: tuple[CompileComparison, ...],
    modes: tuple[str, ...],
    phases: tuple[str, ...],
    max_ratio: float,
    noise_floor_ms: float,
) -> tuple[str, ...]:
    """Describe every gated phase that is unmeasured or slower than ratio plus floor allow."""

    measured: dict[str, CompileComparison] = {
        comparison.mode: comparison for comparison in comparisons
    }
    failures: list[str] = []
    for mode in modes:
        comparison: CompileComparison | None = measured.get(mode)
        if comparison is None:
            failures.append(f"{mode}: no measurement")
            continue
        for phase in phases:
            prefix: str = f"{comparison.kind} {comparison.models} {mode} {phase}"
            base: float | None = comparison.base_timings_ms.get(phase)
            head: float | None = comparison.head_timings_ms.get(phase)
            if base is None or head is None:
                failures.append(f"{prefix}: not reported")
            elif head > base * max_ratio + noise_floor_ms:
                failures.append(
                    f"{prefix}: {head:.0f} ms exceeds {max_ratio:.2f}x base {base:.0f} ms "
                    f"plus {noise_floor_ms:.0f} ms"
                )
    return tuple(failures)


def _measured(seconds: float) -> bool:
    return math.isfinite(seconds) and seconds > 0
