"""Run a seeded series of edits, compiling and judging after each one."""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path

from scripts.delta_compile_series._helpers.edits import edited_file
from scripts.delta_compile_series._helpers.outcomes import judged
from scripts.delta_compile_series.constants import (
    DELTA_WEIGHT,
    EDITS,
    FALLBACK_WEIGHT,
    REVERT_PROBABILITY,
)
from scripts.delta_compile_series.models import (
    DeltaCompileEdit,
    DeltaCompileOutcome,
    DeltaCompileSeries,
)


def run_delta_compile_series(
    *, project_dir: Path, seed: int, steps: int, compile_project: Callable[[], DeltaCompileOutcome]
) -> DeltaCompileSeries:
    """Edit or revert `steps` times, compiling after each, and judge every compile."""

    rng: random.Random = random.Random(seed)
    weights: list[int] = [
        FALLBACK_WEIGHT if edit.fallback_reason else DELTA_WEIGHT for edit in EDITS
    ]
    pending: list[tuple[Path, str, DeltaCompileEdit]] = []
    described: list[str] = []
    unexpected: list[str] = []
    deltas: int = 0
    failing: bool = compile_project().returncode != 0
    for index in range(steps):
        reverted: bool = bool(pending) and (failing or rng.random() < REVERT_PROBABILITY)
        if reverted:
            path, original, edit = pending.pop()
            path.write_text(original, encoding="utf-8")
        else:
            edit: DeltaCompileEdit = rng.choices(EDITS, weights=weights)[0]
            path, original = edited_file(project_dir=project_dir, edit=edit, rng=rng)
            pending.append((path, original, edit))
        step: str = f"step {index}: {'revert ' if reverted else ''}{edit.kind} in {path.name}"
        described.append(step)
        outcome: DeltaCompileOutcome = compile_project()
        others_edited: bool = any(other != path for other, _, _ in pending)
        delta, problem = judged(
            outcome=outcome, edit=edit, reverted=reverted, others_edited=others_edited
        )
        deltas += int(delta)
        if problem is not None:
            unexpected.append(f"{step}: {problem}")
        failing = outcome.returncode != 0
    return DeltaCompileSeries(steps=tuple(described), deltas=deltas, unexpected=tuple(unexpected))
