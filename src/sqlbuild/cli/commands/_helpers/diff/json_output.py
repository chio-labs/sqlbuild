"""Structured JSON output for diff results."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

from sqlbuild.adapter.contract.models import RowDiffCoverage, RowDiffResult, RowDiffSampleRow
from sqlbuild.cli.commands._helpers.diff.evidence import (
    example_value_payload,
    render_example_pair,
)
from sqlbuild.cli.commands._helpers.diff.output import has_diff_failures
from sqlbuild.cli.commands.constants import DEFAULT_DIFF_MAX_VALUE_LENGTH
from sqlbuild.cli.commands.models import DiffExampleRenderOptions
from sqlbuild.executor.diff.constants import DIFF_INPUT_KIND_QUERY
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult

_DEFAULT_EXAMPLE_RENDER_OPTIONS: DiffExampleRenderOptions = DiffExampleRenderOptions(
    max_value_length=DEFAULT_DIFF_MAX_VALUE_LENGTH
)


def render_diff_json_output(
    *,
    result: DiffExecutionResult,
    from_label: str,
    to_label: str,
    example_render_options: DiffExampleRenderOptions = _DEFAULT_EXAMPLE_RENDER_OPTIONS,
    phase_seconds: dict[str, float] | None = None,
    outcome: str | None = None,
) -> str:
    """Render one stable structured diff document."""

    return json.dumps(
        _json_safe_value(
            _diff_payload(
                result=result,
                from_label=from_label,
                to_label=to_label,
                example_render_options=example_render_options,
                phase_seconds=phase_seconds,
                outcome=outcome,
            )
        ),
        allow_nan=False,
        indent=2,
        sort_keys=True,
        default=_json_default,
    )


def render_diff_error_json(*, status: str, code: str, message: str) -> str:
    """Render a machine-readable incomplete or execution-failure outcome."""

    return json.dumps(
        {
            "schema_version": 1,
            "status": status,
            "outcome": status,
            "error": {"code": code, "message": message},
            "models": [],
            "query_comparisons": [],
        },
        indent=2,
        sort_keys=True,
    )


def _json_safe_value(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            label: str = "NaN"
        elif value > 0:
            label = "Infinity"
        else:
            label = "-Infinity"
        return {"kind": "non_finite_number", "value": label}
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe_value(item) for item in value]
    return value


def write_diff_json_output(
    *,
    path: Path | None,
    result: DiffExecutionResult,
    from_label: str,
    to_label: str,
    example_render_options: DiffExampleRenderOptions = _DEFAULT_EXAMPLE_RENDER_OPTIONS,
    phase_seconds: dict[str, float] | None = None,
    outcome: str | None = None,
) -> None:
    """Write a stable structured diff document when a path is requested."""

    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_diff_json_output(
            result=result,
            from_label=from_label,
            to_label=to_label,
            example_render_options=example_render_options,
            phase_seconds=phase_seconds,
            outcome=outcome,
        )
        + "\n",
        encoding="utf-8",
    )


def _diff_payload(
    *,
    result: DiffExecutionResult,
    from_label: str,
    to_label: str,
    example_render_options: DiffExampleRenderOptions,
    phase_seconds: dict[str, float] | None,
    outcome: str | None,
) -> dict[str, object]:
    model_payloads: list[dict[str, object]] = [
        _model_payload(
            model=model,
            from_label=from_label,
            to_label=to_label,
            example_render_options=example_render_options,
        )
        for model in result.model_results
    ]
    resolved_outcome: str = outcome or ("findings" if has_diff_failures(result) else "pass")
    status: str = {
        "pass": "no_differences_found",
        "findings": "differences_found",
    }.get(resolved_outcome, resolved_outcome)
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": status,
        "outcome": resolved_outcome,
        "from": from_label,
        "to": to_label,
        "models": model_payloads,
    }
    query_payloads: list[dict[str, object]] = [
        model_payload
        for model, model_payload in zip(result.model_results, model_payloads, strict=True)
        if model.input_kind == DIFF_INPUT_KIND_QUERY
    ]
    if query_payloads:
        payload["input_kind"] = DIFF_INPUT_KIND_QUERY
        payload["query_comparisons"] = query_payloads
    if phase_seconds is not None:
        payload["phase_seconds"] = {
            phase: round(seconds, 6) for phase, seconds in sorted(phase_seconds.items())
        }
    return payload


def _model_payload(
    *,
    model: ModelDiffResult,
    from_label: str,
    to_label: str,
    example_render_options: DiffExampleRenderOptions,
) -> dict[str, object]:
    rows: RowDiffResult | None = model.row_result
    payload: dict[str, object] = {
        "input_kind": model.input_kind,
        "name": model.name,
        "from_label": from_label,
        "to_label": to_label,
        "from_relation": model.left_relation,
        "to_relation": model.right_relation,
        "unique_key": list(model.unique_key),
        "unkeyed": model.unkeyed,
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
        "population_keys": None if model.unkeyed else rows.population_count,
        "compared_keys": None if model.unkeyed else rows.compared_count,
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
        "column_mismatches": [
            {"column": column.name, "rows": column.mismatched_count}
            for column in rows.column_results
            if column.mismatched_count > 0
        ],
    }
    payload["examples"] = _examples_payload(
        model=model,
        options=example_render_options,
    )
    return payload


def _examples_payload(
    *, model: ModelDiffResult, options: DiffExampleRenderOptions
) -> dict[str, object]:
    unequal_rows: list[dict[str, object]] = []
    values_truncated: bool = False
    sample_row: RowDiffSampleRow
    for sample_row in model.unequal_row_samples:
        cells: list[dict[str, object]] = []
        for cell in sample_row.changed_cells:
            left_value, right_value = render_example_pair(
                left_value=cell.left_value,
                right_value=cell.right_value,
                options=options,
            )
            values_truncated = values_truncated or left_value.truncated or right_value.truncated
            cells.append(
                {
                    "column": cell.name,
                    "from": example_value_payload(left_value),
                    "to": example_value_payload(right_value),
                }
            )
        unequal_rows.append(
            {
                "key": {name: value for name, value in sample_row.key_values},
                "changed_cells": cells,
            }
        )
    rows: RowDiffResult | None = model.row_result
    return {
        "unequal_rows": unequal_rows,
        "from_only_keys": [dict(sample) for sample in model.left_only_key_samples],
        "to_only_keys": [dict(sample) for sample in model.right_only_key_samples],
        "truncated_by_count": bool(
            rows is not None
            and (
                rows.unequal_count > len(model.unequal_row_samples)
                or rows.left_only_count > len(model.left_only_key_samples)
                or rows.right_only_count > len(model.right_only_key_samples)
            )
        ),
        "values_truncated": values_truncated,
        "values_suppressed": options.suppress_values,
        "max_value_length": options.max_value_length,
    }


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
