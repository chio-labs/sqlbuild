"""Orchestrate compile-owned catalogs; native code owns schemas and diagnostics."""

import json
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.classes.binding_catalog import BindingCatalog
from sqlbuild.compiler.sql_analysis.constants import BINDING_SEVERITIES, NATIVE_DIALECT_ALIASES
from sqlbuild.compiler.sql_analysis.exceptions import SqlAnalysisBoundaryError
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingDiagnostic,
    SqlBindingResult,
    SqlSchemaValidationRequest,
)
from sqlbuild.compiler.sql_analysis.types import (
    NativeDiagnosticRow,
    NativePositionsModule,
    NativeValidationModule,
)


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
        if all(request.catalog is None for request in batch):
            payload: str = catalog.native.validation_payload(catalog.prepare(batch))
            responses: object = json.loads(
                cast(NativeValidationModule, _native).validate_sql_with_schemas_json(payload)
            )
            if not isinstance(responses, list) or len(responses) != len(batch):
                raise SqlAnalysisBoundaryError(
                    "native SQL schema validation returned an invalid batch response"
                )
            for (index, request), response in zip(group, responses, strict=True):
                results[index] = _binding_result(
                    sql=request.sql, dialect=request.dialect, response=response
                )
            continue
        rows: list[list[NativeDiagnosticRow]] = catalog.native.binding_results(
            catalog.prepare(batch)
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


def _binding_result(*, sql: str, dialect: str | None, response: object) -> SqlBindingResult:
    if not isinstance(response, dict):
        raise SqlAnalysisBoundaryError("native SQL schema validation returned an invalid response")
    payload: dict[str, Any] = cast(dict[str, Any], response)
    if not isinstance(payload.get("errors"), list):
        raise SqlAnalysisBoundaryError("native SQL schema validation returned an invalid response")
    rows: list[NativeDiagnosticRow] = []
    for value in payload["errors"]:
        if not isinstance(value, dict) or value.get("severity") not in BINDING_SEVERITIES:
            continue
        if not isinstance(value.get("code"), str):
            continue
        rows.append(
            (
                value["code"],
                str(value.get("message") or "SQL binding failed"),
                _optional_int(value.get("line")),
                _optional_int(value.get("column")),
                _optional_int(value.get("start")),
                _optional_int(value.get("end")),
                str(value["severity"]),
            )
        )
    return _result(
        cast(NativePositionsModule, _native).binding_diagnostics(
            sql=sql,
            dialect=NATIVE_DIALECT_ALIASES.get(dialect or "generic", dialect or "generic"),
            rows=rows,
        )
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
