"""Native direct semantic-use extraction helpers."""

from __future__ import annotations

import json
import re
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.lineage._helpers.columns import _normalize_sqlbuild_refs
from sqlbuild.compiler.lineage.exceptions import LineageAnalysisError
from sqlbuild.compiler.lineage.models import (
    DirectSemanticColumnUse,
    PhysicalResource,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import ColumnLineageConfidence, NativeUsageModule


def get_model_semantic_uses(  # noqa: FFS002 - one native request/response translation boundary
    *, model: CompiledModel, schema: dict[str, dict[str, str]], dialect: str | None
) -> tuple[DirectSemanticColumnUse, ...]:
    normalized_sql, physical_resources = _normalize_sqlbuild_refs(model.query_sql)
    resource_by_physical_name: dict[str, PhysicalResource] = {
        resource.physical_name: resource for resource in physical_resources
    }
    tables: list[dict[str, object]] = []
    for name, columns in sorted(schema.items()):
        table_columns: list[dict[str, str]] = []
        for column_name, column_type in columns.items():
            table_columns.append({"name": column_name, "type": column_type})
        tables.append({"name": name, "columns": table_columns})
    request: dict[str, object] = {
        "sql": normalized_sql,
        "dialect": dialect or "generic",
        "schema": {
            "strict": True,
            "tables": tables,
        },
    }
    response: Any = json.loads(
        cast(NativeUsageModule, _native).analyze_sql_uses_json(
            json.dumps(request, separators=(",", ":"), sort_keys=True)
        )
    )
    raw_uses: object = response.get("uses") if isinstance(response, dict) else None
    if not isinstance(raw_uses, list):
        raise LineageAnalysisError("native semantic usage analysis returned an invalid response")
    result: list[DirectSemanticColumnUse] = []
    for raw_use in raw_uses:
        if not isinstance(raw_use, dict):
            continue
        source_name: object = raw_use.get("sourceName")
        column_name: object = raw_use.get("column")
        context: object = raw_use.get("context")
        expression_sql: object = raw_use.get("expressionSql")
        if not all(
            isinstance(value, str) for value in (source_name, column_name, context, expression_sql)
        ):
            continue
        resource: PhysicalResource | None = resource_by_physical_name.get(str(source_name))
        if resource is None:
            continue
        line: int | None
        column: int | None
        line, column = _authored_position(
            authored_sql=model.authored_sql,
            column_name=str(column_name),
            fallback_line=_optional_int(raw_use.get("line")),
            fallback_column=_optional_int(raw_use.get("columnOffset")),
        )
        result.append(
            DirectSemanticColumnUse(
                consumer_model=model.name,
                context=str(context),
                expression_sql=str(expression_sql),
                source=QualifiedLineageColumn(
                    resource_type=resource.resource_type,
                    resource_name=resource.resource_name,
                    column_name=str(column_name),
                ),
                confidence=ColumnLineageConfidence(str(raw_use.get("confidence") or "unknown")),
                line=line,
                column=column,
            )
        )
    return tuple(result)


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _authored_position(
    *,
    authored_sql: str,
    column_name: str,
    fallback_line: int | None,
    fallback_column: int | None,
) -> tuple[int | None, int | None]:
    occurrences: list[re.Match[str]] = list(
        re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(column_name)}(?![A-Za-z0-9_])",
            authored_sql,
        )
    )
    if len(occurrences) != 1:
        return fallback_line, fallback_column
    start: int = occurrences[0].start()
    return authored_sql.count("\n", 0, start) + 1, start - authored_sql.rfind("\n", 0, start)
