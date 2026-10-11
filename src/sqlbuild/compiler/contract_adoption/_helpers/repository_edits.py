"""Metadata-preserving MODEL and source declaration edits, computed natively."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.types import CompiledModelView, CompiledSourceView
from sqlbuild.compiler.contract_adoption.exceptions import ContractAdoptionError
from sqlbuild.compiler.contract_adoption.models import ContractFinding
from sqlbuild.compiler.contract_adoption.types import ContractFindingKind
from sqlbuild.spec.contracts.models import SchemaModelEntry


def edit_model(
    *, model: CompiledModelView, physical_columns: tuple[ColumnInfo, ...], overwrite: bool
) -> tuple[str | None, str | None]:
    schema: SchemaModelEntry | None = model.schema_entry
    return _edit_outcome(
        _native.contract_model_edit(
            (
                model.authored_sql,
                str(model.relative_path),
                schema is not None and schema.model_schema is not None,
                [
                    (
                        column.name,
                        column.type,
                        None if column.location is None else str(column.location.path),
                    )
                    for column in (schema.columns if schema is not None else ())
                ],
                [family.name_pattern for family in (schema.dynamic_columns if schema else ())],
                [(column.name, column.type) for column in physical_columns],
                overwrite,
            )
        )
    )


def edit_source(
    *,
    source: CompiledSourceView,
    physical_columns: tuple[ColumnInfo, ...],
    overwrite: bool,
    contents: str | None = None,
) -> tuple[str | None, str | None]:
    return _edit_outcome(
        _native.contract_source_edit(
            (
                source.source_file.contents if contents is None else contents,
                source.source_file.contents,
                source.name,
                [(column.name, column.type) for column in source.source_entry.columns],
                [(column.name, column.type) for column in physical_columns],
                overwrite,
            )
        )
    )


def _edit_outcome(row: tuple[str | None, str | None, str | None]) -> tuple[str | None, str | None]:
    contents, conflict, failure = row
    if failure is not None:
        raise ContractAdoptionError(failure)
    return contents, conflict


def remaining_findings(
    *, findings: tuple[ContractFinding, ...], overwrite: bool, conflict: str | None
) -> tuple[ContractFinding, ...]:
    if conflict is not None:
        first: ContractFinding | None = findings[0] if findings else None
        if first is None:
            raise ContractAdoptionError("contract ownership conflict requires resource evidence")
        return (
            *findings,
            ContractFinding(
                resource_type=first.resource_type,
                resource_name=first.resource_name,
                kind=ContractFindingKind.OWNERSHIP_CONFLICT,
                message=conflict,
            ),
        )
    resolved: set[ContractFindingKind] = {ContractFindingKind.MISSING_DECLARATION}
    if overwrite:
        resolved.update(
            {ContractFindingKind.TYPE_MISMATCH, ContractFindingKind.MISSING_PHYSICAL_COLUMN}
        )
    return tuple(finding for finding in findings if finding.kind not in resolved)
