"""Public stale-selection warning message formatting entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.pruning.selection_classifier import (
    format_stale_upstream_warning_message as _format_stale_upstream_warning_message,
)


def format_stale_upstream_warning_message(
    *,
    model_label: str,
    model_name: str,
    trigger_label: str,
    trigger_names: tuple[str, ...],
) -> str:
    """Build a multi-line stale-selection warning: summary, capped bullet list, single hint."""

    return _format_stale_upstream_warning_message(
        model_label=model_label,
        model_name=model_name,
        trigger_label=trigger_label,
        trigger_names=trigger_names,
    )
