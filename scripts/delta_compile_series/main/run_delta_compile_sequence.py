"""Compile after each of a fixed sequence of named edits, then once in full."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.delta_compile_series._helpers.sequence import sequence_edited
from scripts.delta_compile_series.constants import (
    COMPILE_REUSE_HIT_LINE,
    DELTA_COMPILE_LINE,
    FAILURE_TAIL_CHARACTERS,
)
from scripts.delta_compile_series.exceptions import DeltaCompileSeriesError
from scripts.delta_compile_series.models import DeltaCompileOutcome, DeltaCompileSequence
from scripts.delta_compile_series.types import SequenceEdit


def run_delta_compile_sequence(
    *,
    project_dir: Path,
    edits: tuple[SequenceEdit, ...],
    compile_project: Callable[[], DeltaCompileOutcome],
    compile_in_full: Callable[[], DeltaCompileOutcome],
) -> DeltaCompileSequence:
    """Compile once, then after each edit, then in full."""

    first: DeltaCompileOutcome = compile_project()
    if first.returncode != 0:
        raise DeltaCompileSeriesError(first.stderr[-FAILURE_TAIL_CHARACTERS:])
    outcomes: list[DeltaCompileOutcome] = []
    for edit in edits:
        _ = sequence_edited(project_dir=project_dir, edit=edit)
        outcomes.append(compile_project())
    full: DeltaCompileOutcome = compile_in_full()
    return DeltaCompileSequence(
        delta_lines=tuple(DELTA_COMPILE_LINE in outcome.stderr for outcome in outcomes),
        replayed_last=COMPILE_REUSE_HIT_LINE in outcomes[-1].stderr,
        last_report=outcomes[-1].stdout,
        full_report=full.stdout,
    )
