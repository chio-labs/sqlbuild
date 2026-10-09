"""Prove a dynamic column contract natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.compiler.analysis_session._helpers.dynamic_contract import native_dynamic_contract
from sqlbuild.compiler.compile.models import DynamicColumnContractProof
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def prove_native_dynamic_contract(
    *,
    query_sql: str,
    dialect: str | None,
    families: tuple[SchemaDynamicColumnFamily, ...],
    column_types_by_table: dict[str, dict[str, str]],
    authoritative_column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
) -> DynamicColumnContractProof | None:
    """Return Python's proof for declared families, or None to prove it in Python."""

    return native_dynamic_contract(
        query_sql=query_sql,
        dialect=dialect,
        families=families,
        column_types_by_table=column_types_by_table,
        authoritative_column_types_by_table=authoritative_column_types_by_table,
        column_nullability_by_table=column_nullability_by_table,
        dynamic_families_by_table=dynamic_families_by_table,
    )
