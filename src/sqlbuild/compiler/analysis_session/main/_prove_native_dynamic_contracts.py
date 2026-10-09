"""Prove dynamic column contracts natively for the preview compiler engine."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.analysis_session._helpers.dynamic_contracts import native_dynamic_contracts
from sqlbuild.compiler.analysis_session.models import NativePivotTables
from sqlbuild.compiler.compile.models import DynamicColumnContractProof
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def prove_native_dynamic_contracts(
    *,
    session: Any | None,
    tables: NativePivotTables,
    models: tuple[tuple[str, tuple[SchemaDynamicColumnFamily, ...]], ...],
) -> tuple[DynamicColumnContractProof | None, ...]:
    """Python's proof per `(sql, families)` model from the session or `tables`; None for Python."""

    return native_dynamic_contracts(session=session, tables=tables, models=models)
