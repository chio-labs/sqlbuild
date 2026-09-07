"""Compare authored contracts with read-only physical evidence."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models import CompiledModel, CompiledSource
from sqlbuild.compiler.contract_adoption._helpers.compare import (
    compare_evidence,
    model_evidence,
    source_evidence,
    unavailable_evidence,
)
from sqlbuild.compiler.contract_adoption.models import ContractEvidence


def compare_contracts(
    *,
    adapter: BaseAdapter,
    connection: object,
    models: tuple[CompiledModel, ...],
    sources: tuple[CompiledSource, ...],
) -> tuple[ContractEvidence, ...]:
    """Compare selected declarations with one bulk read of physical columns."""

    inspectable: list[ContractEvidence] = []
    evidence: list[ContractEvidence] = []
    for model in models:
        inspectable.append(model_evidence(model=model))
    for source in sources:
        item: ContractEvidence = source_evidence(source=source)
        if item.findings:
            evidence.append(item)
        else:
            inspectable.append(item)
    relations: tuple[RelationInfo, ...] = tuple(
        RelationInfo(
            database=item.database,
            schema=item.schema,
            name=item.relation,
            relation_type="",
        )
        for item in inspectable
    )
    try:
        physical_by_relation: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
            adapter.get_columns_for_relations(connection=connection, relations=relations)
        )
    except Exception:
        for item in inspectable:
            evidence.append(unavailable_evidence(item=item))
        return tuple(evidence)
    for item in inspectable:
        physical_columns: tuple[ColumnInfo, ...] | None = physical_by_relation.get(
            RelationInfo(
                database=item.database,
                schema=item.schema,
                name=item.relation,
                relation_type="",
            ).identity
        )
        evidence.append(
            compare_evidence(item=item, physical_columns=physical_columns, adapter=adapter)
        )
    return tuple(evidence)
