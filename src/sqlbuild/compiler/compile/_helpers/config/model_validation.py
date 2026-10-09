"""Compile-time validation of model config combinations."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import (
    MIGRATE_FROM_CONFIG_KEY,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.planner.types import (
    MaterializationType,
)
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.models import (
    SchemaColumn,
)

_QUALIFIED_NAME_SEPARATOR: str = "."

_HISTORY_MATERIALIZATIONS: frozenset[str] = frozenset(
    {MaterializationType.INCREMENTAL, MaterializationType.SNAPSHOT}
)
_MIGRATABLE_MATERIALIZATIONS: frozenset[str] = frozenset(
    {
        MaterializationType.TABLE,
        MaterializationType.VIEW,
        MaterializationType.INCREMENTAL,
        MaterializationType.SNAPSHOT,
    }
)


def validate_column_migration_config(
    *, config_values: dict[str, object], model_name: str, columns: tuple[SchemaColumn, ...]
) -> None:
    """Validate column-level migrate_from declarations as one rename set."""

    declared: tuple[SchemaColumn, ...] = tuple(
        column for column in columns if column.migrate_from is not None
    )
    if not declared:
        return
    materialized: str | None = get_config_str(values=config_values, key="materialized")
    if materialized not in _HISTORY_MATERIALIZATIONS and (
        materialized not in _MIGRATABLE_MATERIALIZATIONS
        or config_values.get(MIGRATE_FROM_CONFIG_KEY) is None
    ):
        raise CompileInputError(
            f"model '{model_name}': column '{declared[0].name}' declares migrate_from, which is "
            "only valid for incremental and snapshot models, or for table and view models "
            "that declare migrate_from themselves (the old name's compatibility view then "
            f"presents the column under its old name); '{materialized}' models are rebuilt "
            "with their new columns",
            help="remove migrate_from from the column, or declare the model's own migrate_from",
        )
    sources: dict[str, str] = {}
    column: SchemaColumn
    for column in declared:
        origin: str = (column.migrate_from or "").strip()
        if not origin or _QUALIFIED_NAME_SEPARATOR in origin:
            raise CompileInputError(
                f"model '{model_name}': column '{column.name}' migrate_from must name one "
                "column of the model's existing table",
                help="write the old column name, for example revenue (migrate_from amount)",
            )
        if origin.lower() == column.name.lower():
            raise CompileInputError(
                f"model '{model_name}': column '{column.name}' migrate_from cannot name the "
                "column itself"
            )
        claimed_by: str | None = sources.get(origin.lower())
        if claimed_by is not None:
            raise CompileInputError(
                f"model '{model_name}': columns '{claimed_by}' and '{column.name}' both "
                f"declare migrate_from {origin}; a column can be renamed to only one new name",
                help="keep migrate_from on the column that should receive the existing data",
            )
        sources[origin.lower()] = column.name
    destinations: dict[str, str] = {column.name.lower(): column.name for column in declared}
    for column in declared:
        chained: str | None = destinations.get((column.migrate_from or "").strip().lower())
        if chained is not None:
            raise CompileInputError(
                f"model '{model_name}': column '{column.name}' migrates from "
                f"'{column.migrate_from}', which itself declares migrate_from; chained or "
                "swapped column renames are not supported",
                help=(
                    "a chain or swap cannot be renamed in place safely; give the new column a "
                    "name no other renamed column uses, or rebuild the model with --full-refresh"
                ),
            )
