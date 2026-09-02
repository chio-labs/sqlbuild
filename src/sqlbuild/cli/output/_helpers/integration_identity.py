"""Canonical integration resource identity resolution."""

from __future__ import annotations

from sqlbuild.cli.output.constants import INTEGRATION_CHECK_KINDS, INTEGRATION_LOADER_KIND

_MODEL_RESOURCE_KINDS: frozenset[str] = frozenset({"custom", "model", "snapshot", "table", "view"})


def integration_resource_id(
    *, resource_kind: str, resource_name: str, check_id: str | None, loader_name: str | None = None
) -> str:
    """Return the canonical resource identifier for an integration result."""

    if resource_kind in INTEGRATION_CHECK_KINDS:
        return check_id or ""
    if resource_kind in _MODEL_RESOURCE_KINDS:
        return f"model:{resource_name}"
    if resource_kind == INTEGRATION_LOADER_KIND and loader_name is not None:
        return f"source:{resource_name}"
    return f"{resource_kind}:{resource_name}"
