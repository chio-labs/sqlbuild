"""Public prephase cause annotation entrypoint."""

from __future__ import annotations

from sqlbuild.executor.clone._helpers.prephase_progress import (
    format_prephase_cause_annotation as _format_prephase_cause_annotation,
)


def format_prephase_cause_annotation(caused_by_names: tuple[str, ...]) -> str:
    """Format selected-model causes for a prephase row."""

    return _format_prephase_cause_annotation(caused_by_names)
