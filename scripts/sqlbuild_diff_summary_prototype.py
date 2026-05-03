"""Hardcoded SQLBuild-shaped diff summary prototype.

This prototype is intentionally separate from the generic visual baseline.
It keeps the terminal quality bar high while centering SQLBuild's own
environment/model-oriented semantics.
"""

from __future__ import annotations

from rich import box
from rich.columns import Columns as RichColumns
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

width = 110


def main() -> None:
    console: Console = Console(width=width)
    render_summary(console=console, summary=build_summary())
    console.print()
    console.print(Text("=" * width, style="dim"))
    console.print()
    render_summary(console=console, summary=build_split_summary())


def build_summary() -> dict[str, object]:
    return {
        "title": "SQLBuild Diff Summary",
        "model_name": "orders_snapshot",
        "from_label": "prod",
        "to_label": "dev",
        "primary_key": ("order_id",),
        "comparison": "bounded 7d",
        "excluded_columns": ("status",),
        "tolerances": ("amount_cents: absolute=1",),
        "schema_message": "No schema differences.",
        "rows": {
            "from_count": 10,
            "to_count": 10,
            "from_only_count": 0,
            "equal_count": 8,
            "unequal_count": 2,
            "to_only_count": 0,
        },
        "changed_columns": (
            {"name": "amount_cents", "mismatches": 2, "match_rate": 0.8},
            {"name": "payment_method", "mismatches": 1, "match_rate": 0.9},
            {"name": "ordered_at", "mismatches": 1, "match_rate": 0.9},
        ),
        "examples": (
            {
                "name": "amount_cents",
                "examples": (
                    "order_id=1 | Classic Belgian | 1700 -> 1702",
                    "order_id=8 | Liege | 950 -> 955",
                ),
            },
            {
                "name": "payment_method",
                "examples": ("order_id=3 | Chicken and Waffle | cash -> credit_card",),
            },
            {
                "name": "ordered_at",
                "examples": (
                    "order_id=9 | Chicken and Waffle | 2026-04-04 10:00:00 -> 2026-04-04 10:05:00",
                ),
            },
        ),
    }


def build_split_summary() -> dict[str, object]:
    return {
        "title": "SQLBuild Diff Summary",
        "model_name": "orders_snapshot",
        "from_label": "prod",
        "to_label": "dev",
        "primary_key": ("order_id",),
        "comparison": "full",
        "excluded_columns": ("status",),
        "tolerances": (),
        "schema_message": "No schema differences.",
        "rows": {
            "from_count": 10,
            "to_count": 11,
            "from_only_count": 2,
            "equal_count": 6,
            "unequal_count": 2,
            "to_only_count": 3,
        },
        "changed_columns": (
            {"name": "amount_cents", "mismatches": 2, "match_rate": 0.75},
            {"name": "waffle_name", "mismatches": 1, "match_rate": 0.875},
        ),
        "examples": (
            {
                "name": "amount_cents",
                "examples": (
                    "order_id=1 | Classic Belgian | 1700 -> 1705",
                    "order_id=8 | Liege | 950 -> 975",
                ),
            },
            {
                "name": "waffle_name",
                "examples": ("order_id=5 | Classic Belgian -> Brussels",),
            },
        ),
    }


def render_summary(*, console: Console, summary: dict[str, object]) -> None:
    console.print(
        Panel(
            Text(str(summary["title"]), style="bold", justify="center"),
            box=box.HEAVY,
        )
    )
    console.print(
        Text(
            f"{summary['from_label']} vs {summary['to_label']}",
            style="bold cyan",
            justify="center",
        )
    )
    console.print()
    console.print(_render_overview(summary))
    console.print()
    _print_section(console, "Schemas", Text(str(summary["schema_message"]), style="italic"))
    _print_section(
        console,
        "Rows",
        _render_rows(
            rows=summary["rows"],
            from_label=str(summary["from_label"]),
            to_label=str(summary["to_label"]),
        ),
    )
    _print_section(console, "Changed Columns", _render_changed_columns(summary["changed_columns"]))
    _print_section(console, "Examples", _render_examples(summary["examples"]))


def _render_overview(summary: dict[str, object]) -> RenderableType:
    table: Table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    primary_key: tuple[str, ...] = tuple(summary["primary_key"])
    excluded_columns: tuple[str, ...] = tuple(summary["excluded_columns"])
    tolerances: tuple[str, ...] = tuple(summary["tolerances"])
    table.add_row("Model", str(summary["model_name"]))
    table.add_row("Key", ", ".join(primary_key))
    table.add_row("Comparison", str(summary["comparison"]))
    table.add_row("Excluded", ", ".join(excluded_columns))
    if tolerances:
        table.add_row("Tolerances", ", ".join(tolerances))
    return table


def _print_section(console: Console, title: str, content: RenderableType) -> None:
    console.print(Text(title, style="bold"))
    console.print(Text("▔" * len(title), style="bold"))
    console.print(content)
    console.print()


def _render_rows(rows: object, from_label: str, to_label: str) -> RenderableType:
    row_summary: dict[str, int] = dict(rows)
    counts: Table = Table.grid(padding=(0, 2))
    counts.add_column(justify="center")
    counts.add_column(justify="center")
    counts.add_column(justify="center")
    counts.add_row(f"{from_label} count", "", f"{to_label} count")
    counts.add_row(
        f"{row_summary['from_count']:,}",
        _render_delta_label(row_summary["from_count"], row_summary["to_count"]),
        f"{row_summary['to_count']:,}",
    )

    joined_count: int = row_summary["equal_count"] + row_summary["unequal_count"]
    renderables: list[RenderableType] = []
    left_box: Table = Table(show_header=False, padding=0, box=box.HEAVY_EDGE)
    right_box: Table = Table(show_header=False, padding=0, box=box.HEAVY_EDGE)
    for _ in range(5):
        left_box.add_column()
        right_box.add_column()

    if row_summary["from_only_count"] > 0:
        left_box.add_row(*([Text("-", style="red")] * 5))
        left_box.add_section()
    if row_summary["equal_count"] > 0:
        left_box.add_row(*([" "] * 5))
        left_box.add_section()
        right_box.add_row(*([" "] * 5))
        right_box.add_section()
    if row_summary["unequal_count"] > 0:
        left_box.add_row(*([" "] * 5))
        right_box.add_row(*([" "] * 5))
        right_box.add_section()
    if row_summary["to_only_count"] > 0:
        right_box.add_row(*([Text("+", style="green")] * 5))

    renderables.append(left_box)
    renderables.append(_render_row_separator(row_summary))
    renderables.append(Group("\n", right_box) if row_summary["from_only_count"] > 0 else right_box)
    renderables.append(_render_row_stats(row_summary, joined_count, from_label, to_label))
    renderables.append(_render_joined_annotation(row_summary, joined_count))

    return Group(counts, "", RichColumns(renderables, padding=0), "", f"joined: {joined_count:,}")


def _render_delta_label(from_count: int, to_count: int) -> str:
    if from_count == 0:
        return "(no baseline)"
    if from_count == to_count:
        return "(no change)"
    if to_count > from_count:
        return f"(+{((to_count / from_count) - 1):.2%})"
    return f"(-{(1 - (to_count / from_count)):.2%})"


def _render_row_separator(rows: dict[str, int]) -> RenderableType:
    joined: list[RenderableType] = []
    if rows["from_only_count"] > 0:
        joined.append("\n")
    if rows["equal_count"] > 0:
        joined.append("╌" * 3)
        joined.append(Text(" = ", style="bold"))
    if rows["unequal_count"] > 0:
        joined.append("╌" * 3)
        joined.append(Text(" ≠ ", style="bold"))
    joined.append("╌" * 3)
    return Group(*joined)


def _render_row_stats(
    rows: dict[str, int],
    joined_count: int,
    from_label: str,
    to_label: str,
) -> RenderableType:
    table: Table = Table(show_header=False, box=box.ROUNDED, padding=(0, 0, 0, 1))
    table.add_column(justify="right")
    table.add_column(justify="left")
    table.add_column(justify="right")
    table.add_row(
        f"{rows['from_only_count']:,}",
        f"{from_label} only",
        f"({_format_percentage(rows['from_only_count'], rows['from_count'])})",
    )
    table.add_section()
    table.add_row(
        f"{rows['equal_count']:,}",
        "equal",
        f"({_format_percentage(rows['equal_count'], joined_count)})",
    )
    table.add_section()
    table.add_row(
        f"{rows['unequal_count']:,}",
        "unequal",
        f"({_format_percentage(rows['unequal_count'], joined_count)})",
    )
    table.add_section()
    table.add_row(
        f"{rows['to_only_count']:,}",
        f"{to_label} only",
        f"({_format_percentage(rows['to_only_count'], rows['to_count'])})",
    )
    return table


def _render_joined_annotation(rows: dict[str, int], joined_count: int) -> RenderableType:
    if joined_count == 0:
        return ""
    lines: list[RenderableType] = []
    if rows["from_only_count"] > 0:
        lines.append("\n")
    lines.append("╌╮")
    lines.append(" │")
    if rows["equal_count"] > 0 and rows["unequal_count"] > 0:
        lines.append(f"╌├╴  {joined_count:,}  joined")
        lines.append(" │")
    lines.append("╌╯")
    return Group(*lines)


def _render_changed_columns(columns: object) -> RenderableType:
    table: Table = Table(show_header=False)
    table.add_column(style="cyan", max_width=32, overflow="fold")
    table.add_column(justify="right")
    table.add_column(justify="right")
    column: dict[str, object]
    for column in tuple(columns):
        table.add_row(
            str(column["name"]),
            f"mismatches={int(column['mismatches']):,}",
            f"match={_format_percentage(float(column['match_rate']), 1.0)}",
        )
    return table


def _render_examples(columns: object) -> RenderableType:
    blocks: list[RenderableType] = []
    column: dict[str, object]
    for column in tuple(columns):
        blocks.append(Text(str(column["name"]), style="bold cyan"))
        example: str
        for example in tuple(column["examples"]):
            blocks.append(f"  - {example}")
        blocks.append("")
    return Group(*blocks[:-1])


def _format_percentage(numerator: int | float, denominator: int | float) -> str:
    if denominator == 0:
        return "0.00%"
    return f"{(numerator / denominator):.2%}"


if __name__ == "__main__":
    main()
