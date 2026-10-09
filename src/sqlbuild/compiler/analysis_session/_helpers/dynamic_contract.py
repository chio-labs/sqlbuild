"""Prove one model's dynamic column contract natively, outside the analysis session."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.analysis_session._helpers.deferral_records import record_analysis_deferral
from sqlbuild.compiler.analysis_session._helpers.session_rows import (
    contract_proof,
    family_rows,
    shape_rows,
)
from sqlbuild.compiler.analysis_session.constants import CONTRACT_DEFERRED, DEFERRAL_DYNAMIC_PIVOT
from sqlbuild.compiler.analysis_session.types import ContractRow, ShapeRows
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.compile.models import DynamicColumnContractProof
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def native_dynamic_contract(
    *,
    query_sql: str,
    dialect: str | None,
    families: tuple[SchemaDynamicColumnFamily, ...],
    column_types_by_table: dict[str, dict[str, str]],
    authoritative_column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
) -> DynamicColumnContractProof | None:
    """Python's proof for declared families, or None (recorded) where Python must prove it."""

    shapes: tuple[ShapeRows | None, ...] = (
        shape_rows(column_types_by_table),
        shape_rows(authoritative_column_types_by_table),
        shape_rows(column_nullability_by_table),
    )
    row: ContractRow = (CONTRACT_DEFERRED, None)
    if all(rows is not None for rows in shapes):
        row = _native.prove_dynamic_column_contract(
            (
                dialect or "generic",
                shapes[0] or [],
                shapes[1] or [],
                shapes[2] or [],
                family_rows(dynamic_families_by_table),
                query_sql,
                [PythonModelAnalysis.family_row(family) for family in families],
            )
        )
    if row[0] == CONTRACT_DEFERRED:
        record_analysis_deferral(kind=DEFERRAL_DYNAMIC_PIVOT)
    return contract_proof(row[1])
