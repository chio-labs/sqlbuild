"""Output helpers for the diff command."""

from __future__ import annotations

from rich import box
from rich.columns import Columns as RichColumns
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from sqlbuild.adapter.shared.models import RowDiffColumnResult, RowDiffResult, SchemaDiffResult
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult

_WIDTH: int = 110
_TOP_CHANGED_COLUMNS: int = 5


def render_diff_output(
    *,
    result: DiffExecutionResult,
    from_label: str,
    to_label: str,
    mode_label: str,
    use_color: bool,
) -> str:
    """Render a concise Rich terminal summary for a diff result."""

    console: Console = Console(force_terminal=use_color, color_system="auto", width=_WIDTH)
    with console.capture() as capture:
        if not result.model_results:
            console.print("No models selected for diff.")
        else:
            console.print(
                Panel(
                    Text("SQLBuild Diff Summary", style="bold", justify="center"),
                    box=box.HEAVY,
                )
            )
            console.print(Text(f"{from_label} vs {to_label}", style="bold cyan", justify="center"))
            console.print(Text(f"selected models: {len(result.model_results):,}", justify="center"))
            console.print()
            model_result: ModelDiffResult
            for index, model_result in enumerate(result.model_results):
                if index > 0:
                    console.print()
                    console.print(Text("─" * _WIDTH, style="dim"))
                    console.print()
                _render_model_result(
                    console=console,
                    model_result=model_result,
                    from_label=from_label,
                    to_label=to_label,
                    mode_label=mode_label,
                )
    return capture.get().rstrip()


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


def _render_model_result(
    *,
    console: Console,
    model_result: ModelDiffResult,
    from_label: str,
    to_label: str,
    mode_label: str,
) -> None:
    console.print(
        _render_overview(
            model_result=model_result,
            mode_label=mode_label,
        )
    )
    console.print()
    _print_section(console=console, title="Schemas", content=_render_schema_summary(model_result))
    if model_result.row_result is not None:
        _print_section(
            console=console,
            title="Rows",
            content=_render_rows(
                rows=model_result.row_result,
                from_label=from_label,
                to_label=to_label,
            ),
        )
        _print_section(
            console=console,
            title="Changed Columns",
            content=_render_changed_columns(model_result),
        )


def _render_overview(*, model_result: ModelDiffResult, mode_label: str) -> RenderableType:
    table: Table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_row("Model", model_result.name)
    table.add_row("Key", _primary_key_label(model_result))
    table.add_row("Comparison", _mode_display(model_result=model_result, mode_label=mode_label))
    if model_result.bounded_fallback:
        table.add_row("Fallback", "no cursor configured; used full row diff")
    if model_result.excluded_columns:
        table.add_row("Excluded", ", ".join(model_result.excluded_columns))
    tolerance_label: str | None = _tolerance_label(model_result.row_result)
    if tolerance_label is not None:
        table.add_row("Tolerances", tolerance_label)
    return table


def _primary_key_label(model_result: ModelDiffResult) -> str:
    if not model_result.unique_key:
        return "<not used>"
    return ", ".join(model_result.unique_key)


def _mode_display(*, model_result: ModelDiffResult, mode_label: str) -> str:
    if model_result.bounded_fallback:
        return f"{mode_label} (fallback to full row diff)"
    return mode_label


def _tolerance_label(row_result: RowDiffResult | None) -> str | None:
    if row_result is None:
        return None
    labels: list[str] = []
    column: RowDiffColumnResult
    for column in row_result.column_results:
        if column.tolerance is None:
            continue
        parts: list[str] = []
        if column.tolerance.absolute is not None:
            parts.append(f"absolute={column.tolerance.absolute}")
        if column.tolerance.relative is not None:
            parts.append(f"relative={column.tolerance.relative}")
        labels.append(f"{column.name} {' '.join(parts)}")
    if not labels:
        return None
    return ", ".join(labels)


def _render_schema_summary(model_result: ModelDiffResult) -> RenderableType:
    schema_result: SchemaDiffResult = model_result.schema_result
    schema_diff_count: int = (
        len(schema_result.added_columns)
        + len(schema_result.removed_columns)
        + len(schema_result.type_changed_columns)
    )
    if (
        not schema_result.added_columns
        and not schema_result.removed_columns
        and not schema_result.type_changed_columns
    ):
        return Group("schema differences: 0", Text("No schema differences.", style="italic"))
    lines: list[str] = [f"schema differences: {schema_diff_count:,}"]
    if schema_result.added_columns:
        lines.append(f"added columns: {len(schema_result.added_columns):,}")
    if schema_result.removed_columns:
        lines.append(f"removed columns: {len(schema_result.removed_columns):,}")
    if schema_result.type_changed_columns:
        lines.append(f"type changes: {len(schema_result.type_changed_columns):,}")
    return Group(*lines)


def _print_section(*, console: Console, title: str, content: RenderableType) -> None:
    console.print(Text(title, style="bold"))
    console.print(Text("▔" * len(title), style="bold"))
    console.print(content)
    console.print()


def _render_rows(*, rows: RowDiffResult, from_label: str, to_label: str) -> RenderableType:
    counts: Table = Table.grid(padding=(0, 2))
    counts.add_column(justify="center")
    counts.add_column(justify="center")
    counts.add_column(justify="center")
    counts.add_row(f"{from_label} count", "", f"{to_label} count")
    counts.add_row(
        f"{rows.left_count:,}",
        _render_delta_label(rows.left_count, rows.right_count),
        f"{rows.right_count:,}",
    )

    joined_count: int = rows.equal_count + rows.unequal_count
    renderables: list[RenderableType] = []
    left_box: Table = Table(show_header=False, padding=0, box=box.HEAVY_EDGE)
    right_box: Table = Table(show_header=False, padding=0, box=box.HEAVY_EDGE)
    for _ in range(5):
        left_box.add_column()
        right_box.add_column()

    if rows.left_only_count > 0:
        left_box.add_row(*([Text("-", style="red")] * 5))
        left_box.add_section()
    if rows.equal_count > 0:
        left_box.add_row(*([" "] * 5))
        left_box.add_section()
        right_box.add_row(*([" "] * 5))
        right_box.add_section()
    if rows.unequal_count > 0:
        left_box.add_row(*([" "] * 5))
        right_box.add_row(*([" "] * 5))
        right_box.add_section()
    if rows.right_only_count > 0:
        right_box.add_row(*([Text("+", style="green")] * 5))

    renderables.append(left_box)
    renderables.append(_render_row_separator(rows))
    renderables.append(Group("\n", right_box) if rows.left_only_count > 0 else right_box)
    renderables.append(_render_row_stats(rows, joined_count, from_label, to_label))
    renderables.append(_render_joined_annotation(rows, joined_count))

    return Group(counts, "", RichColumns(renderables, padding=0), "", f"joined: {joined_count:,}")


def _render_delta_label(left_count: int, right_count: int) -> str:
    if left_count == 0:
        return "(no baseline)"
    if left_count == right_count:
        return "(no change)"
    if right_count > left_count:
        return f"(+{((right_count / left_count) - 1):.2%})"
    return f"(-{(1 - (right_count / left_count)):.2%})"


def _render_row_separator(rows: RowDiffResult) -> RenderableType:
    joined: list[RenderableType] = []
    if rows.left_only_count > 0:
        joined.append("\n")
    if rows.equal_count > 0:
        joined.append("╌" * 3)
        joined.append(Text(" = ", style="bold"))
    if rows.unequal_count > 0:
        joined.append("╌" * 3)
        joined.append(Text(" ≠ ", style="bold"))
    joined.append("╌" * 3)
    return Group(*joined)


def _render_row_stats(
    rows: RowDiffResult,
    joined_count: int,
    from_label: str,
    to_label: str,
) -> RenderableType:
    table: Table = Table(show_header=False, box=box.ROUNDED, padding=(0, 0, 0, 1))
    table.add_column(justify="right")
    table.add_column(justify="left")
    table.add_column(justify="right")
    table.add_row(
        f"{rows.left_only_count:,}",
        f"{from_label} only",
        f"({_format_percentage(rows.left_only_count, rows.left_count)})",
    )
    table.add_section()
    table.add_row(
        f"{rows.equal_count:,}",
        "equal",
        f"({_format_percentage(rows.equal_count, joined_count)})",
    )
    table.add_section()
    table.add_row(
        f"{rows.unequal_count:,}",
        "unequal",
        f"({_format_percentage(rows.unequal_count, joined_count)})",
    )
    table.add_section()
    table.add_row(
        f"{rows.right_only_count:,}",
        f"{to_label} only",
        f"({_format_percentage(rows.right_only_count, rows.right_count)})",
    )
    return table


def _render_joined_annotation(rows: RowDiffResult, joined_count: int) -> RenderableType:
    if joined_count == 0:
        return ""
    lines: list[RenderableType] = []
    if rows.left_only_count > 0:
        lines.append("\n")
    lines.append("╌╮")
    lines.append(" │")
    if rows.equal_count > 0 and rows.unequal_count > 0:
        lines.append(f"╌├╴  {joined_count:,}  joined")
        lines.append(" │")
    lines.append("╌╯")
    return Group(*lines)


def _render_changed_columns(model_result: ModelDiffResult) -> RenderableType:
    row_result: RowDiffResult | None = model_result.row_result
    if row_result is None:
        return Text("Schema-only diff; row comparison skipped.", style="italic")
    mismatched_columns: tuple[RowDiffColumnResult, ...] = tuple(
        sorted(
            (column for column in row_result.column_results if column.mismatched_count > 0),
            key=lambda column: (-column.mismatched_count, column.name),
        )
    )
    if not mismatched_columns:
        return Text("No changed columns.", style="italic")
    table: Table = Table(show_header=False)
    table.add_column(style="cyan", max_width=32, overflow="fold")
    table.add_column(justify="right")
    table.add_column(justify="right")
    visible_columns: tuple[RowDiffColumnResult, ...] = mismatched_columns[:_TOP_CHANGED_COLUMNS]
    column: RowDiffColumnResult
    for column in visible_columns:
        match_rate: str = _format_percentage(
            _matching_rows(row_result, column),
            row_result.joined_count,
        )
        table.add_row(
            column.name,
            f"mismatches={column.mismatched_count:,}",
            f"match={match_rate}",
        )
    if len(mismatched_columns) > len(visible_columns):
        table.add_section()
        table.add_row(
            Text("...", style="dim"),
            Text(f"and {len(mismatched_columns) - len(visible_columns):,} more", style="dim"),
            Text("", style="dim"),
        )
    return table


def _matching_rows(row_result: RowDiffResult, column: RowDiffColumnResult) -> int:
    return max(row_result.joined_count - column.mismatched_count, 0)


def _format_percentage(numerator: int | float, denominator: int | float) -> str:
    if denominator == 0:
        return "0.00%"
    return f"{(numerator / denominator):.2%}"
