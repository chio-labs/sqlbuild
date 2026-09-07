"""Physical contract evidence comparison helpers."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.compiler.compile.models import CompiledModel, CompiledSource
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.contract_adoption.models import ContractEvidence, ContractFinding
from sqlbuild.compiler.contract_adoption.types import ContractFindingKind
from sqlbuild.spec.contracts.models import SourceEntry


def model_evidence(*, model: CompiledModel) -> ContractEvidence:
    return ContractEvidence(
        resource_type=CompiledResourceType.MODEL,
        resource_name=model.name,
        database=model.destination.database,
        schema=model.destination.schema,
        relation=model.destination.name,
        declared_columns=tuple(
            ColumnInfo(name=column.name, type=column.type or "")
            for column in (model.schema_entry.columns if model.schema_entry is not None else ())
        ),
        physical_columns=None,
        source_path=model.relative_path,
    )


def source_evidence(*, source: CompiledSource) -> ContractEvidence:
    entry: SourceEntry = source.source_entry
    relation: str | None = entry.table or entry.name
    findings: tuple[ContractFinding, ...] = ()
    if entry.expression is not None or not relation:
        findings = (
            ContractFinding(
                resource_type=CompiledResourceType.SOURCE,
                resource_name=source.name,
                kind=ContractFindingKind.INSPECTION_UNAVAILABLE,
                message="source expression has no inspectable physical relation",
            ),
        )
    return ContractEvidence(
        resource_type=CompiledResourceType.SOURCE,
        resource_name=source.name,
        database=entry.database,
        schema=entry.schema,
        relation=relation or source.name,
        declared_columns=tuple(
            ColumnInfo(name=column.name, type=column.type or "") for column in entry.columns
        ),
        physical_columns=None,
        source_path=source.source_file.relative_path,
        findings=findings,
    )


def compare_evidence(
    *,
    item: ContractEvidence,
    physical_columns: tuple[ColumnInfo, ...] | None,
    adapter: BaseAdapter,
) -> ContractEvidence:
    if physical_columns is None:
        return replace(
            item,
            findings=(
                ContractFinding(
                    resource_type=item.resource_type,
                    resource_name=item.resource_name,
                    kind=ContractFindingKind.RELATION_MISSING,
                    message=f"physical relation {_qualified(item=item)} does not exist",
                ),
            ),
        )
    findings: list[ContractFinding] = []
    declared_by_name: dict[str, ColumnInfo] = {
        column.name.casefold(): column for column in item.declared_columns
    }
    physical_by_name: dict[str, ColumnInfo] = {
        column.name.casefold(): column for column in physical_columns
    }
    for physical in physical_columns:
        declared: ColumnInfo | None = declared_by_name.get(physical.name.casefold())
        if declared is None or not declared.type:
            findings.append(
                ContractFinding(
                    resource_type=item.resource_type,
                    resource_name=item.resource_name,
                    kind=ContractFindingKind.MISSING_DECLARATION,
                    column_name=physical.name,
                    physical_type=physical.type,
                    message=(
                        f"physical column '{physical.name}' ({physical.type}) is not declared"
                        if declared is None
                        else f"declared column '{declared.name}' has no type; "
                        f"physical type is {physical.type}"
                    ),
                )
            )
        elif not types_equal(
            left=declared.type,
            right=physical.type,
            dialect=adapter.sql_analysis_dialect(),
        ):
            findings.append(
                ContractFinding(
                    resource_type=item.resource_type,
                    resource_name=item.resource_name,
                    kind=ContractFindingKind.TYPE_MISMATCH,
                    column_name=declared.name,
                    declared_type=declared.type,
                    physical_type=physical.type,
                    message=(
                        f"column '{declared.name}' is declared {declared.type} but physical "
                        f"type is {physical.type}"
                    ),
                )
            )
    for declared in item.declared_columns:
        if declared.name.casefold() not in physical_by_name:
            findings.append(
                ContractFinding(
                    resource_type=item.resource_type,
                    resource_name=item.resource_name,
                    kind=ContractFindingKind.MISSING_PHYSICAL_COLUMN,
                    column_name=declared.name,
                    declared_type=declared.type or None,
                    message=(
                        f"declared column '{declared.name}' is absent from the physical relation"
                    ),
                )
            )
    return replace(
        item,
        physical_columns=physical_columns,
        findings=tuple(findings),
    )


def unavailable_evidence(*, item: ContractEvidence) -> ContractEvidence:
    return replace(
        item,
        findings=(
            ContractFinding(
                resource_type=item.resource_type,
                resource_name=item.resource_name,
                kind=ContractFindingKind.INSPECTION_UNAVAILABLE,
                message=f"physical relation {_qualified(item=item)} could not be inspected",
            ),
        ),
    )


def _qualified(*, item: ContractEvidence) -> str:
    return ".".join(value for value in (item.database, item.schema, item.relation) if value)
