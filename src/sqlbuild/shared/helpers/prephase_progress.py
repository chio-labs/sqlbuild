"""Shared prephase progress output."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.models import PrephaseProgressRow

_TYPE_WIDTH: int = 10
_NAME_WIDTH: int = 40
_MAX_CAUSE_NAMES: int = 4


def write_prephase_header(*, stream: TextIO, title: str, use_color: bool) -> None:
    """Write a shared prephase header."""

    style: CliStyle = CliStyle(use_color=use_color)
    stream.write(f"\n{style.object_name('Prephase')}  {style.muted(title)}\n\n")
    stream.flush()


def write_prephase_rows(
    *, stream: TextIO, rows: tuple[PrephaseProgressRow, ...], use_color: bool
) -> None:
    """Write shared prephase result rows."""

    if not rows:
        return
    total: int = len(rows)
    row: PrephaseProgressRow
    for index, row in enumerate(rows, start=1):
        write_prephase_row(
            stream=stream,
            row=row,
            index=index,
            total=total,
            use_color=use_color,
        )
    stream.flush()


def write_prephase_row(
    *, stream: TextIO, row: PrephaseProgressRow, index: int, total: int, use_color: bool
) -> None:
    """Write one shared prephase result row."""

    style: CliStyle = CliStyle(use_color=use_color)
    index_width: int = len(str(total)) * 2 + 1
    ctr: str = f"{index}/{total}".rjust(index_width)
    name: str = _truncate(row.name, _NAME_WIDTH)
    status: str = style.status(row.status)
    duration: str = _format_duration(row.duration_seconds)
    detail: str = row.detail
    cause: str = format_prephase_cause_annotation(row.caused_by_names)
    suffix: str = "".join(part for part in (detail, cause) if part)
    stream.write(
        f"  {ctr}  {row.label:<{_TYPE_WIDTH}}{name:<{_NAME_WIDTH}} {status:<6} {duration}{suffix}\n"
    )
    stream.flush()


def format_prephase_cause_annotation(caused_by_names: tuple[str, ...]) -> str:
    """Format selected-model causes for a prephase row."""

    names: tuple[str, ...] = tuple(sorted(frozenset(name for name in caused_by_names if name)))
    if not names:
        return ""
    displayed: tuple[str, ...] = names[:_MAX_CAUSE_NAMES]
    extra_count: int = len(names) - len(displayed)
    content: str = ", ".join(displayed)
    if extra_count > 0:
        content = f"{content} and {extra_count} more"
    return f"  [for {content}]"


def _format_duration(duration_seconds: float | None) -> str:
    if duration_seconds is None:
        return ""
    return f"{duration_seconds:.2f}s"


def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."
