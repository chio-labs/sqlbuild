"""Validate logical namespaces required by preserve target values."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import PRESERVE_TARGET_VALUE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.spec.contracts.models import TargetConfig


def validate_preserved_logical_namespace(
    *,
    resource_label: str,
    logical_database: str | None,
    logical_schema: str | None,
    target_config: TargetConfig | None,
) -> None:
    """Fail when preserve cannot retain a resource-owned logical namespace."""

    if target_config is None:
        return
    missing: list[str] = []
    if target_config.database == PRESERVE_TARGET_VALUE and logical_database is None:
        missing.append("database")
    if target_config.schema == PRESERVE_TARGET_VALUE and logical_schema is None:
        missing.append("schema")
    if not missing:
        return
    dimensions: str = " and ".join(missing)
    raise CompileInputError(
        f"{resource_label} has no logical {dimensions}, but the selected target sets "
        f"{dimensions} to 'preserve'",
        help=(
            f"Set {dimensions} on the resource or its defaults, or configure a literal target "
            f"{dimensions}."
        ),
    )
