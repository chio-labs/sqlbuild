"""Output helpers for the diff command."""

from __future__ import annotations

from rich import box
from rich.columns import Columns as RichColumns
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from sqlbuild.adapter.shared.models import (
    RowDiffColumnResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    SchemaDiffResult,
)
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult

_WIDTH: int = 110
_TOP_CHANGED_COLUMNS: int = 5
_RICH_TITLE_STYLE: str = "bold"
_RICH_OBJECT_STYLE: str = "bold cyan"
_RICH_SECTION_STYLE: str = "bold"
_RICH_ADDED_STYLE: str = "green"
_RICH_REMOVED_STYLE: str = "red"
_RICH_MUTED_STYLE: str = "dim"


def render_diff_output(
    *,
    result: DiffExecutionResult,
    from_label: str,
    to_label: str,
    mode_label: str,
    use_color: bool,
    verbose: bool,
    max_column_examples: int,
    max_row_only_examples: int,
) -> str:
    """Render a concise Rich terminal summary for a diff result."""

    console: Console = Console(force_terminal=use_color, color_system="auto", width=_WIDTH)
    with console.capture() as capture:
        if not result.model_results:
            console.print("No models selected for diff.")
        else:
            console.print(
                Panel(
                    Text("SQLBuild Diff Summary", style=_RICH_TITLE_STYLE, justify="center"),
                    box=box.HEAVY,
                )
            )
            console.print(
                Text(f"{from_label} vs {to_label}", style=_RICH_OBJECT_STYLE, justify="center")
            )
            console.print(Text(f"selected models: {len(result.model_results):,}", justify="center"))
            console.print()
            model_result: ModelDiffResult
            for index, model_result in enumerate(result.model_results):
                if index > 0:
                    console.print()
                    console.print(Text("─" * _WIDTH, style=_RICH_MUTED_STYLE))
                    console.print()
                _render_model_result(
                    console=console,
                    model_result=model_result,
                    from_label=from_label,
                    to_label=to_label,
                    mode_label=mode_label,
                    verbose=verbose,
                    max_column_examples=max_column_examples,
                    max_row_only_examples=max_row_only_examples,
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
    verbose: bool,
    max_column_examples: int,
    max_row_only_examples: int,
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
            content=_render_changed_columns(
                model_result,
                verbose=verbose,
                max_column_examples=max_column_examples,
            ),
        )
        if verbose and model_result.unequal_row_samples:
            example_content: RenderableType | None = _render_examples(
                model_result,
                max_column_examples=max_column_examples,
            )
            if example_content is not None:
                _print_section(
                    console=console,
                    title="Examples",
                    content=example_content,
                )
        if model_result.left_only_key_samples:
            _print_section(
                console=console,
                title=f"{from_label} only",
                content=_render_side_only_samples(
                    side_label=from_label,
                    key_samples=model_result.left_only_key_samples,
                    max_row_only_examples=max_row_only_examples,
                ),
            )
        if model_result.right_only_key_samples:
            _print_section(
                console=console,
                title=f"{to_label} only",
                content=_render_side_only_samples(
                    side_label=to_label,
                    key_samples=model_result.right_only_key_samples,
                    max_row_only_examples=max_row_only_examples,
                ),
            )


def _render_overview(*, model_result: ModelDiffResult, mode_label: str) -> RenderableType:
    table: Table = Table.grid(padding=(0, 2))
    table.add_column(style=_RICH_OBJECT_STYLE, justify="right")
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
        return Text("No schema differences.", style="italic")
    lines: list[str] = [f"schema differences: {schema_diff_count:,}"]
    if schema_result.added_columns:
        lines.append(f"added columns: {len(schema_result.added_columns):,}")
    if schema_result.removed_columns:
        lines.append(f"removed columns: {len(schema_result.removed_columns):,}")
    if schema_result.type_changed_columns:
        lines.append(f"type changes: {len(schema_result.type_changed_columns):,}")
    return Group(*lines)


def _print_section(*, console: Console, title: str, content: RenderableType) -> None:
    console.print(Text(title, style=_RICH_SECTION_STYLE))
    console.print(Text("▔" * len(title), style=_RICH_SECTION_STYLE))
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
        _render_delta_label(rows.left_count, right_count=rows.right_count),
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
        left_box.add_row(*([Text("-", style=_RICH_REMOVED_STYLE)] * 5))
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
        right_box.add_row(*([Text("+", style=_RICH_ADDED_STYLE)] * 5))

    renderables.append(left_box)
    renderables.append(_render_row_separator(rows))
    renderables.append(Group("\n", right_box) if rows.left_only_count > 0 else right_box)
    renderables.append(
        _render_row_stats(rows, joined_count=joined_count, from_label=from_label, to_label=to_label)
    )
    renderables.append(_render_joined_annotation(rows, joined_count=joined_count))

    return Group(counts, "", RichColumns(renderables, padding=0), "", f"joined: {joined_count:,}")


def _render_delta_label(left_count: int, *, right_count: int) -> str:
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
        joined.append(Text(" = ", style=_RICH_SECTION_STYLE))
    if rows.unequal_count > 0:
        joined.append("╌" * 3)
        joined.append(Text(" ≠ ", style=_RICH_SECTION_STYLE))
    joined.append("╌" * 3)
    return Group(*joined)


def _render_row_stats(
    rows: RowDiffResult,
    *,
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
        f"({_format_percentage(rows.left_only_count, denominator=rows.left_count)})",
    )
    table.add_section()
    table.add_row(
        f"{rows.equal_count:,}",
        "equal",
        f"({_format_percentage(rows.equal_count, denominator=joined_count)})",
    )
    table.add_section()
    table.add_row(
        f"{rows.unequal_count:,}",
        "unequal",
        f"({_format_percentage(rows.unequal_count, denominator=joined_count)})",
    )
    table.add_section()
    table.add_row(
        f"{rows.right_only_count:,}",
        f"{to_label} only",
        f"({_format_percentage(rows.right_only_count, denominator=rows.right_count)})",
    )
    return table


def _render_joined_annotation(rows: RowDiffResult, *, joined_count: int) -> RenderableType:
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


def _render_changed_columns(
    model_result: ModelDiffResult,
    *,
    verbose: bool,
    max_column_examples: int,
) -> RenderableType:
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
    table.add_column(style=_RICH_OBJECT_STYLE, max_width=32, overflow="fold")
    table.add_column(justify="right")
    table.add_column(justify="right")
    visible_columns: tuple[RowDiffColumnResult, ...] = mismatched_columns[:_TOP_CHANGED_COLUMNS]
    column: RowDiffColumnResult
    for column in visible_columns:
        match_rate: str = _format_percentage(
            _matching_rows(row_result, column=column),
            denominator=row_result.joined_count,
        )
        table.add_row(
            column.name,
            f"mismatches={column.mismatched_count:,}",
            f"match={match_rate}",
        )
    if len(mismatched_columns) > len(visible_columns):
        table.add_section()
        table.add_row(
            Text("...", style=_RICH_MUTED_STYLE),
            Text(
                f"and {len(mismatched_columns) - len(visible_columns):,} more",
                style=_RICH_MUTED_STYLE,
            ),
            Text("", style=_RICH_MUTED_STYLE),
        )
    if not verbose:
        example_content: RenderableType | None = _render_examples(
            model_result,
            max_column_examples=max_column_examples,
            visible_column_names=tuple(column.name for column in visible_columns),
        )
        if example_content is not None:
            return Group(
                table,
                "",
                example_content,
                "",
                Text("Use --verbose to show more example row changes.", style=_RICH_MUTED_STYLE),
            )
        return table
    return table


def _matching_rows(row_result: RowDiffResult, *, column: RowDiffColumnResult) -> int:
    return max(row_result.joined_count - column.mismatched_count, 0)


def _format_percentage(numerator: int | float, *, denominator: int | float) -> str:
    if denominator == 0:
        return "0.00%"
    return f"{(numerator / denominator):.2%}"


def _render_examples(
    model_result: ModelDiffResult,
    *,
    max_column_examples: int,
    visible_column_names: tuple[str, ...] | None = None,
) -> RenderableType | None:
    blocks: list[RenderableType] = []
    grouped_examples: dict[str, list[str]] = {}
    sample_row: RowDiffSampleRow
    for sample_row in model_result.unequal_row_samples:
        key_label: str = ", ".join(f"{key}={value}" for key, value in sample_row.key_values)
        cell: RowDiffSampleCell
        for cell in sample_row.changed_cells:
            grouped_examples.setdefault(cell.name, []).append(
                f"{key_label} | {cell.left_value} -> {cell.right_value}"
            )
    column_name: str
    for column_name in sorted(grouped_examples):
        if visible_column_names is not None and column_name not in visible_column_names:
            continue
        blocks.append(Text(column_name, style=_RICH_OBJECT_STYLE))
        all_examples: list[str] = grouped_examples[column_name]
        visible_examples: list[str] = all_examples[:max_column_examples]
        example: str
        for example in visible_examples:
            blocks.append(f"  - {example}")
        if len(all_examples) > len(visible_examples):
            blocks.append(
                Text(
                    f"  showing {len(visible_examples):,} of {len(all_examples):,} examples",
                    style=_RICH_MUTED_STYLE,
                )
            )
        blocks.append("")
    return Group(*blocks[:-1]) if blocks else None


def _render_side_only_samples(
    *,
    side_label: str,
    key_samples: tuple[tuple[tuple[str, object], ...], ...],
    max_row_only_examples: int,
) -> RenderableType:
    blocks: list[RenderableType] = []
    visible_samples: tuple[tuple[tuple[str, object], ...], ...] = key_samples[
        :max_row_only_examples
    ]
    sample: tuple[tuple[str, object], ...]
    for sample in visible_samples:
        blocks.append("  - " + " | ".join(f"{key}={value}" for key, value in sample))
    if len(key_samples) > len(visible_samples):
        truncation_message: str = (
            f"  showing {len(visible_samples):,} of {len(key_samples):,} {side_label} only rows"
        )
        blocks.append(
            Text(
                truncation_message,
                style=_RICH_MUTED_STYLE,
            )
        )
    return Group(*blocks) if blocks else Text("No side-only samples collected.", style="italic")
