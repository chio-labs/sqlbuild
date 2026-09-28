"""Resolve how long a migrated model keeps a compatibility view at its old name."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.migrations.constants import OLD_NAME_VIEW_CONFIG_KEY


def resolve_old_name_view_retention(
    *, config_values: Mapping[str, object], project_retention: str | None
) -> str | None:
    """Return the model's retention text, the project's when unset, or None when disabled."""

    if OLD_NAME_VIEW_CONFIG_KEY not in config_values:
        return project_retention
    value: object = config_values[OLD_NAME_VIEW_CONFIG_KEY]
    if value is False:
        return None
    return str(value).strip()
