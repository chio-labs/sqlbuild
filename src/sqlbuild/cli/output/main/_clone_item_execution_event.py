"""Public direct clone item event formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_protocol_v1 import (
    format_clone_item_execution_event as _format_clone_item_execution_event,
)
from sqlbuild.executor.clone.models import CloneItemResult


def format_clone_item_execution_event(*, item: CloneItemResult, resource_type: str) -> str:
    """Format one completed clone item as a JSON Lines event."""

    return _format_clone_item_execution_event(item=item, resource_type=resource_type)
