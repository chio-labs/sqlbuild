"""Orchestrate compile-owned catalogs; native code owns schemas and diagnostics."""

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.classes.binding_catalog import BindingCatalog
from sqlbuild.compiler.sql_analysis.constants import NATIVE_DIALECT_ALIASES
from sqlbuild.compiler.sql_analysis.exceptions import SqlAnalysisBoundaryError
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingDiagnostic,
    SqlBindingResult,
    SqlSchemaValidationRequest,
)
from sqlbuild.compiler.sql_analysis.types import NativeDiagnosticRow


def get_schema_validations(
    *, requests: tuple[SqlSchemaValidationRequest, ...]
) -> tuple[SqlBindingResult, ...]:
    if not requests:
        return ()
    catalogs: dict[tuple[str, bool, tuple[str, ...], tuple[str, ...]], BindingCatalog] = {}
    groups: dict[BindingCatalog, list[tuple[int, SqlSchemaValidationRequest]]] = {}
    for index, request in enumerate(requests):
        dialect: str = NATIVE_DIALECT_ALIASES.get(
            request.dialect or "generic", request.dialect or "generic"
        )
        key: tuple[str, bool, tuple[str, ...], tuple[str, ...]] = (
            dialect,
            request.quoted_identifiers_ignore_case,
            request.known_functions,
            request.known_types,
        )
        catalog: BindingCatalog | None = request.catalog or catalogs.get(key)
        if catalog is None:
            catalog = BindingCatalog(
                dialect=dialect,
                quoted_ignore_case=request.quoted_identifiers_ignore_case,
                known_functions=request.known_functions,
                known_types=request.known_types,
                relations=request.schema,
            )
            catalogs[key] = catalog
        groups.setdefault(catalog, []).append((index, request))
    results: list[SqlBindingResult] = [SqlBindingResult()] * len(requests)
    for catalog, group in groups.items():
        batch: list[SqlSchemaValidationRequest] = [request for _, request in group]
        rows: list[list[NativeDiagnosticRow]] = (
            _native.schema_validation_rows(catalog.native, catalog.dialect, catalog.prepare(batch))
            if all(request.catalog is None for request in batch)
            else catalog.native.binding_results(catalog.prepare(batch))
        )
        if len(rows) != len(batch):
            raise SqlAnalysisBoundaryError(
                "native SQL schema validation returned an invalid batch response"
            )
        for (index, _), diagnostics in zip(group, rows, strict=True):
            results[index] = _result(diagnostics)
    return tuple(results)


def _result(rows: list[NativeDiagnosticRow]) -> SqlBindingResult:
    return SqlBindingResult(diagnostics=tuple(SqlBindingDiagnostic(*row) for row in rows))
