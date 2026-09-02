"""Resolve model-level cursor policy overrides."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.spec.contracts.constants import CURSOR_POLICY_DISABLED
from sqlbuild.spec.contracts.models import FutureCursorsConfig, StartCursorsConfig
from sqlbuild.spec.contracts.types import FutureCursorAction


def resolve_start_cursor_config(
    *, model: CompiledModel, project_config: StartCursorsConfig | None
) -> StartCursorsConfig | None:
    """Resolve automatic-start policy with model config taking precedence."""

    configured: StartCursorsConfig = project_config or StartCursorsConfig()
    raw_distance: object | None = model.config.values.get("cursor_start_max_ahead")
    raw_action: object | None = model.config.values.get("cursor_start_max_action")
    max_ahead: str | None = configured.max_ahead
    if isinstance(raw_distance, str):
        max_ahead = None if raw_distance == CURSOR_POLICY_DISABLED else raw_distance
    action: FutureCursorAction = configured.action
    if isinstance(raw_action, str):
        action = FutureCursorAction(raw_action)
    return StartCursorsConfig(max_ahead=max_ahead, action=action) if max_ahead is not None else None


def resolve_future_cursor_config(
    *, model: CompiledModel, project_config: FutureCursorsConfig | None
) -> FutureCursorsConfig | None:
    """Resolve future-end policy with model config taking precedence."""

    configured: FutureCursorsConfig = project_config or FutureCursorsConfig()
    raw_distance: object | None = model.config.values.get("cursor_future_max_distance")
    raw_action: object | None = model.config.values.get("cursor_future_action")
    max_distance: str | None = configured.max_distance
    if isinstance(raw_distance, str):
        max_distance = None if raw_distance == CURSOR_POLICY_DISABLED else raw_distance
    action: FutureCursorAction = configured.action
    if isinstance(raw_action, str):
        action = FutureCursorAction(raw_action)
    return (
        FutureCursorsConfig(max_distance=max_distance, action=action)
        if max_distance is not None
        else None
    )
