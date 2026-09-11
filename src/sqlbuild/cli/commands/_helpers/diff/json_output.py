"""Structured JSON output for diff results."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from sqlbuild.adapter.contract.models import RowDiffCoverage, RowDiffResult
from sqlbuild.cli.commands._helpers.diff.output import has_diff_failures
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult


def write_diff_json_output(
    *,
    path: Path | None,
    result: DiffExecutionResult,
    from_label: str,
    to_label: str,
) -> None:
    """Write a stable structured diff document when a path is requested."""

    if path is None:
        return
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "differences_found" if has_diff_failures(result) else "no_differences_found",
        "from": from_label,
        "to": to_label,
        "models": [_model_payload(model=model) for model in result.model_results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _model_payload(*, model: ModelDiffResult) -> dict[str, object]:
    rows: RowDiffResult | None = model.row_result
    payload: dict[str, object] = {
        "name": model.name,
        "from_relation": model.left_relation,
        "to_relation": model.right_relation,
        "unique_key": list(model.unique_key),
        "excluded_columns": list(model.excluded_columns),
        "schema": {
            "added_columns": [column.name for column in model.schema_result.added_columns],
            "removed_columns": [column.name for column in model.schema_result.removed_columns],
            "type_changed_columns": [
                {"name": left.name, "from_type": left.type, "to_type": right.type}
                for left, right in model.schema_result.type_changed_columns
            ],
        },
    }
    if rows is None:
        payload["comparison_scope"] = "schema_only"
        return payload
    payload["comparison_scope"] = "exhaustive" if rows.is_exhaustive else "sampled"
    payload["coverage"] = {
        "requested": {
            "cursor_column": rows.cursor_column,
            "start": rows.cursor_start,
            "end": rows.cursor_end,
        },
        "from": _coverage_payload(coverage=rows.left_coverage),
        "to": _coverage_payload(coverage=rows.right_coverage),
        "differs": _coverage_differs(rows=rows),
    }
    payload["sampling"] = {
        "configured_row_limit": rows.sampling.row_limit if rows.sampling is not None else None,
        "seed": rows.sampling.seed if rows.sampling is not None else None,
        "population_keys": rows.population_count,
        "compared_keys": rows.compared_count,
        "coverage_ratio": (
            rows.compared_count / rows.population_count if rows.population_count else 1.0
        ),
        "exhaustive": rows.is_exhaustive,
    }
    payload["rows"] = {
        "from_count": rows.left_count,
        "to_count": rows.right_count,
        "joined_count": rows.equal_count + rows.unequal_count,
        "equal_count": rows.equal_count,
        "unequal_count": rows.unequal_count,
        "from_only_count": rows.left_only_count,
        "to_only_count": rows.right_only_count,
        "changed_columns": {column.name: column.mismatched_count for column in rows.column_results},
    }
    return payload


def _coverage_payload(*, coverage: RowDiffCoverage | None) -> dict[str, object] | None:
    if coverage is None:
        return None
    return {
        "row_count": coverage.row_count,
        "minimum_cursor": coverage.minimum_cursor,
        "maximum_cursor": coverage.maximum_cursor,
    }


def _coverage_differs(*, rows: RowDiffResult) -> bool:
    if rows.cursor_column is None or rows.left_coverage is None or rows.right_coverage is None:
        return False
    return (
        rows.left_coverage.minimum_cursor != rows.right_coverage.minimum_cursor
        or rows.left_coverage.maximum_cursor != rows.right_coverage.maximum_cursor
    )


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)
