"""Prove dynamic column contracts natively for models outside the analysis session."""

from __future__ import annotations

from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.analysis_session._helpers.session_rows import (
    contract_proof,
    family_rows,
    shape_rows,
)
from sqlbuild.compiler.analysis_session.models import NativePivotTables
from sqlbuild.compiler.analysis_session.types import ContractRow
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.compile.models import DynamicColumnContractProof
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily

type _ModelRow = tuple[str, list[tuple[str, str, str, str, str, str | None]]]


def native_dynamic_contracts(
    *,
    session: Any | None,
    tables: NativePivotTables,
    models: tuple[tuple[str, tuple[SchemaDynamicColumnFamily, ...]], ...],
) -> tuple[DynamicColumnContractProof | None, ...]:
    """Each model's proof in order; a native internal failure raises."""

    if not models:
        return ()
    rows: list[_ModelRow] = [_model_row(sql=sql, families=families) for sql, families in models]
    contracts: list[ContractRow] = (
        session.prove_dynamic_contracts(rows)
        if session is not None
        else _native.prove_dynamic_column_contracts(
            (
                tables.dialect or "generic",
                shape_rows(tables.column_types_by_table),
                shape_rows(tables.authoritative_column_types_by_table),
                shape_rows(tables.column_nullability_by_table),
                family_rows(tables.dynamic_families_by_table),
                rows,
            )
        )
    )
    return tuple(contract_proof(proof) for _, proof in contracts)


def _model_row(*, sql: str, families: tuple[SchemaDynamicColumnFamily, ...]) -> _ModelRow:
    return (sql, list(map(PythonModelAnalysis.family_row, families)))
