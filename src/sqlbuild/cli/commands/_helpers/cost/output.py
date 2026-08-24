"""Shared cost breakdown and history presentation."""

from __future__ import annotations

import shutil
from datetime import UTC
from decimal import Decimal

from sqlbuild.cli.commands.constants import (
    BYTE_SCALE,
    BYTE_UNIT,
    COST_HISTORY_NUMERIC_COLUMNS,
    COST_NARROW_TERMINAL_WIDTH,
    COST_RESOURCE_NUMERIC_START_COLUMN,
    TERABYTE_UNIT,
)
from sqlbuild.cost.constants import DEFAULT_RATE_SOURCE
from sqlbuild.cost.models import CostRunRecord, ResourceCost, RunCostSummary
from sqlbuild.cost.types import CostStatus
from sqlbuild.presentation.classes.cli_style import CliStyle


def format_cost_breakdown(
    *,
    record: CostRunRecord,
    use_color: bool,
    limit: int | None = None,
    terminal_width: int | None = None,
    show_run_id: bool = True,
) -> str:
    """Format one run using the same aligned table for build and drill-down output."""

    style: CliStyle = CliStyle(use_color=use_color)
    width: int = terminal_width or shutil.get_terminal_size(fallback=(100, 24)).columns
    heading: str = style.title("Cost")
    status: str = _styled_cost_status(style=style, status=record.cost.status)
    rate_note: str = (
        style.warning(f"default ${record.cost.usd_per_credit:.2f}/credit")
        if record.cost.rate_source == DEFAULT_RATE_SOURCE
        else style.muted(f"${record.cost.usd_per_credit:.2f}/credit")
    )
    total: str = (
        f"{heading}  {style.value(_format_usd(record.cost.estimated_usd))} estimated  |  "
        f"{style.value(_format_credits(record.cost.estimated_compute_credits))}  |  "
        f"{rate_note}"
    )
    if not record.cost.resources and record.cost.status != CostStatus.COMPLETE:
        status_lines: list[str] = [f"{heading}  {status}"]
        if show_run_id:
            status_lines.append(f"{style.label('Run')}  {record.run_id}")
        if record.cost.message:
            status_lines.append(style.muted(record.cost.message))
        status_lines.extend(style.warning(limitation) for limitation in record.cost.limitations)
        status_lines.append(
            style.muted(f"Run `sqb cost {record.run_id}` to inspect this run later.")
        )
        return "\n".join(status_lines)
    lines: list[str] = [total]
    if record.cost.status != CostStatus.COMPLETE:
        lines.append(status)
    if show_run_id:
        lines.append(f"{style.label('Run')}  {record.run_id}")
    resources: tuple[ResourceCost, ...] = (
        record.cost.resources if limit is None else record.cost.resources[:limit]
    )
    if resources:
        lines.extend(
            (
                "",
                *_format_resource_rows(
                    resources=resources,
                    total=record.cost,
                    style=style,
                    width=width,
                ),
            )
        )
    if limit is not None and len(record.cost.resources) > limit:
        remaining: int = len(record.cost.resources) - limit
        lines.append(
            style.muted(
                f"Showing {limit} of {len(record.cost.resources)} by estimated cost; "
                f"`sqb cost {record.run_id}` for all models ({remaining} more)."
            )
        )
    if record.cost.message:
        lines.append(style.muted(record.cost.message))
    if record.cost.rate_source == DEFAULT_RATE_SOURCE:
        lines.append(
            style.warning("Configure cost.usd_per_credit with your Snowflake contract rate.")
        )
    lines.extend(style.warning(limitation) for limitation in record.cost.limitations)
    lines.append(
        style.muted(
            "Estimate uses fair-share visible warehouse busy time; it is not Snowflake-billed "
            "credits or invoice reconciliation."
        )
    )
    return "\n".join(lines)


def format_cost_history(
    *, records: tuple[CostRunRecord, ...], matching_count: int, use_color: bool
) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [style.title("SQLBuild cost history")]
    if not records:
        return "\n".join(
            (
                lines[0],
                style.muted("No persisted cost runs."),
                style.muted(f"Showing 0 of {matching_count} matching runs."),
            )
        )
    headings: tuple[str, ...] = (
        "Completed (UTC)",
        "Run",
        "Build",
        "Cost",
        "Attributed credits",
        "Est. USD",
    )
    rows: list[tuple[str, ...]] = [
        (
            record.completed_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            record.run_id,
            record.build_status,
            record.cost.status.value,
            f"{record.cost.estimated_compute_credits:.6f}",
            _format_usd(record.cost.estimated_usd),
        )
        for record in records
    ]
    widths: list[int] = _column_widths(headings=headings, rows=rows)
    lines.append("  ".join(heading.ljust(widths[index]) for index, heading in enumerate(headings)))
    for row in rows:
        lines.append(
            "  ".join(
                (
                    value.rjust(widths[index])
                    if index in COST_HISTORY_NUMERIC_COLUMNS
                    else value.ljust(widths[index])
                )
                for index, value in enumerate(row)
            )
        )
    lines.append(
        style.muted(
            f"Showing {len(records)} of {matching_count} matching runs. "
            "Run `sqb cost <run_id>` for a full breakdown."
        )
    )
    return "\n".join(lines)


def _format_resource_rows(
    *,
    resources: tuple[ResourceCost, ...],
    total: RunCostSummary,
    style: CliStyle,
    width: int,
) -> tuple[str, ...]:
    if width < COST_NARROW_TERMINAL_WIDTH:
        headings: tuple[str, ...] = ("Model", "Attributed credits", "Est. cost")
        rows: list[tuple[str, ...]] = [
            (
                _truncate(value=resource.resource_name, limit=32),
                f"{resource.estimated_compute_credits:.6f}",
                _format_usd(resource.estimated_usd),
            )
            for resource in resources
        ]
        rows.append(
            (
                "TOTAL",
                f"{total.estimated_compute_credits:.6f}",
                _format_usd(total.estimated_usd),
            )
        )
        return _format_table_rows(
            headings=headings,
            rows=rows,
            numeric_start=COST_RESOURCE_NUMERIC_START_COLUMN - 1,
            style=style,
        )
    headings: tuple[str, ...] = (
        "Model",
        "Warehouse",
        "Busy share",
        "Scanned",
        "Attributed credits",
        "Est. cost",
    )
    rows: list[tuple[str, ...]] = [
        (
            _truncate(value=resource.resource_name, limit=36),
            _truncate(value=resource.warehouse_name, limit=20),
            f"{resource.attributed_seconds:.2f}s",
            _format_bytes(resource.bytes_scanned),
            f"{resource.estimated_compute_credits:.6f}",
            _format_usd(resource.estimated_usd),
        )
        for resource in resources
    ]
    rows.append(
        (
            "TOTAL",
            "",
            f"{total.attributed_seconds:.2f}s",
            _format_bytes(total.bytes_scanned),
            f"{total.estimated_compute_credits:.6f}",
            _format_usd(total.estimated_usd),
        )
    )
    return _format_table_rows(
        headings=headings,
        rows=rows,
        numeric_start=COST_RESOURCE_NUMERIC_START_COLUMN,
        style=style,
    )


def _styled_cost_status(*, style: CliStyle, status: CostStatus) -> str:
    if status == CostStatus.COMPLETE:
        return style.value(status.value)
    if status in {CostStatus.PARTIAL, CostStatus.PENDING}:
        return style.warning(status.value)
    if status == CostStatus.COLLECTION_FAILED:
        return style.error(status.value)
    return style.muted(status.value)


def _format_usd(value: Decimal) -> str:
    return f"${value:.4f}"


def _format_credits(value: Decimal) -> str:
    return f"{value:.6f} attributed credits"


def _format_bytes(value: int) -> str:
    size: Decimal = Decimal(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < BYTE_SCALE or unit == TERABYTE_UNIT:
            return f"{size:.1f} {unit}" if unit != BYTE_UNIT else f"{int(size)} {BYTE_UNIT}"
        size /= Decimal(BYTE_SCALE)
    return f"{value} B"


def _truncate(*, value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _column_widths(*, headings: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[int]:
    widths: list[int] = []
    for index, heading in enumerate(headings):
        column_widths: list[int] = [len(row[index]) for row in rows]
        widths.append(max(len(heading), *column_widths))
    return widths


def _format_table_rows(
    *,
    headings: tuple[str, ...],
    rows: list[tuple[str, ...]],
    numeric_start: int,
    style: CliStyle,
) -> tuple[str, ...]:
    widths: list[int] = _column_widths(headings=headings, rows=rows)
    output: list[str] = [
        style.label("  ".join(value.ljust(widths[index]) for index, value in enumerate(headings)))
    ]
    for row in rows:
        cells: list[str] = []
        for index, value in enumerate(row):
            padded: str = (
                value.rjust(widths[index]) if index >= numeric_start else value.ljust(widths[index])
            )
            cells.append(style.object_name(padded) if index == 0 else style.value(padded))
        output.append("  ".join(cells))
    return tuple(output)
