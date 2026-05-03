"""Output helpers for the diff command."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import RowDiffColumnResult, RowDiffResult, SchemaDiffResult
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult


def render_diff_output(*, result: DiffExecutionResult) -> str:
    """Render a compact human-readable diff result."""

    if not result.model_results:
        return "No models selected for diff."
    lines: list[str] = ["Diff results"]
    model_result: ModelDiffResult
    for model_result in result.model_results:
        lines.extend(_render_model_result(model_result))
    return "\n".join(lines)


def has_diff_failures(result: DiffExecutionResult) -> bool:
    """Return true when any selected model has schema or row differences."""

    model_result: ModelDiffResult
    for model_result in result.model_results:
        schema_result: SchemaDiffResult = model_result.schema_result
        if (
            schema_result.added_columns
            or schema_result.removed_columns
            or schema_result.type_changed_columns
        ):
            return True
        row_result: RowDiffResult | None = model_result.row_result
        if row_result is not None and (
            row_result.unequal_count or row_result.left_only_count or row_result.right_only_count
        ):
            return True
    return False


def _render_model_result(model_result: ModelDiffResult) -> list[str]:
    lines: list[str] = ["", f"{model_result.name}"]
    lines.append(f"from: {model_result.left_relation}")
    lines.append(f"to:   {model_result.right_relation}")
    schema_result: SchemaDiffResult = model_result.schema_result
    schema_diff_count: int = (
        len(schema_result.added_columns)
        + len(schema_result.removed_columns)
        + len(schema_result.type_changed_columns)
    )
    lines.append(f"schema differences: {schema_diff_count}")
    row_result: RowDiffResult | None = model_result.row_result
    if row_result is None:
        return lines
    if model_result.bounded_fallback:
        lines.append("bounded diff: no cursor configured; used full row diff")
    lines.append(
        "rows: "
        f"left={row_result.left_count} right={row_result.right_count} "
        f"joined={row_result.joined_count} equal={row_result.equal_count} "
        f"unequal={row_result.unequal_count} left_only={row_result.left_only_count} "
        f"right_only={row_result.right_only_count}"
    )
    mismatched_columns: tuple[RowDiffColumnResult, ...] = tuple(
        column for column in row_result.column_results if column.mismatched_count
    )
    if mismatched_columns:
        column_summary: str = ", ".join(
            f"{column.name}={column.mismatched_count}" for column in mismatched_columns
        )
        lines.append(f"column mismatches: {column_summary}")
    return lines
