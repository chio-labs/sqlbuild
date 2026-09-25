"""Native semantic diagnostics survive the SQLBuild boundary and dialect gate."""

from __future__ import annotations

import json
from typing import Any

import pytest

import sqlbuild._native as native
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.models import SqlBindingResult, SqlSchemaValidationRequest
from tests.unit.src.sqlbuild.compiler.sql_analysis.main._test_types import (
    SemanticDiagnosticMappingCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticDiagnosticMappingCase(
            description="semantic and prepared type diagnostics",
            expected_codes=(
                "B101",
                "B102",
                "B004",
                "B005",
                "B210",
                "B211",
                "B212",
                "B213",
                "B214",
                "B215",
                "B216",
                "B217",
                "B218",
                "B219",
                "B230",
                "B231",
                "B232",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_native_semantic_errors_when_validating_then_codes_and_locations_survive(
    monkeypatch: pytest.MonkeyPatch,
    test_case: SemanticDiagnosticMappingCase,
) -> None:
    codes: dict[str, str] = {"E202": "B101", "E203": "B102", "E222": "B004", "E223": "B005"}
    codes.update({f"E{number}": f"B{number}" for number in (*range(210, 220), 230, 231, 232)})

    def validate(payload: str) -> str:
        requests: list[dict[str, Any]] = json.loads(payload)
        assert all(request["options"]["semantic"] for request in requests)
        assert all(not request["options"]["check_types"] for request in requests)
        errors: list[dict[str, object]] = [
            {
                "code": code,
                "severity": "error",
                "message": "Invalid expression",
                "line": 2,
                "column": 8,
            }
            for code in codes
        ]
        return json.dumps([{"errors": errors}] * len(requests))

    monkeypatch.setattr(native, "validate_sql_with_schemas_json", validate)
    results: tuple[SqlBindingResult, ...] = get_schema_validations(
        requests=tuple(
            SqlSchemaValidationRequest(sql="SELECT\n  invalid", dialect=dialect, schema={})
            for dialect in ("duckdb", "snowflake", "postgres", "bigquery")
        )
    )
    for result in results:
        assert (
            tuple(diagnostic.code for diagnostic in result.diagnostics) == test_case.expected_codes
        )
        assert all(
            (diagnostic.line, diagnostic.column) == (2, 8) for diagnostic in result.diagnostics
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
