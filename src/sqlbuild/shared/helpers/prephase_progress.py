"""Shared prephase progress output."""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.models import PrephaseProgressRow

_TYPE_WIDTH: int = 10
_NAME_WIDTH: int = 40
_MAX_CAUSE_NAMES: int = 4


def run_prephase_clone_stream[RESULT](
    *,
    stream: TextIO,
    title: str,
    caused_by_names: tuple[str, ...],
    use_color: bool,
    run_clone: Callable[[Callable[[int, int, CloneItemResult], None]], RESULT],
) -> RESULT:
    """Run clone work with shared prephase streaming output."""

    write_prephase_header(stream=stream, title=title, use_color=use_color)
    _write_prephase_transient_status(stream=stream, message="Cloning...")

    def on_item(index: int, total: int, item: CloneItemResult) -> None:
        _clear_prephase_transient_status(stream=stream)
        write_prephase_row(
            stream=stream,
            row=prephase_row_from_clone_item(item=item, caused_by_names=caused_by_names),
            index=index,
            total=total,
            use_color=use_color,
        )
        if index < total:
            _write_prephase_transient_status(
                stream=stream,
                message=f"Cloning {index + 1}/{total}...",
            )

    try:
        return run_clone(on_item)
    finally:
        _clear_prephase_transient_status(stream=stream)


def prephase_row_from_clone_item(
    *, item: CloneItemResult, caused_by_names: tuple[str, ...]
) -> PrephaseProgressRow:
    """Build a shared prephase row from a clone item result."""

    return PrephaseProgressRow(
        label=clone_item_label(item),
        name=item.name,
        status=clone_item_status(item),
        duration_seconds=item.duration_seconds,
        caused_by_names=caused_by_names,
    )


def clone_item_label(item: CloneItemResult) -> str:
    """Return the shared prephase row label for a clone item action."""

    if item.action == CloneAction.RECREATED_VIEW:
        return "view"
    if item.action == CloneAction.COPIED:
        return "copy"
    return "clone"


def clone_item_status(item: CloneItemResult) -> str:
    """Return the shared prephase row status token for a clone item status."""

    if item.status == CloneStatus.SUCCESS:
        return "OK"
    if item.status == CloneStatus.WARNING:
        return "WARN"
    return "FAIL"


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


def _stream_is_tty(stream: TextIO) -> bool:
    return hasattr(stream, "isatty") and stream.isatty()


def _write_prephase_transient_status(*, stream: TextIO, message: str) -> None:
    if not _stream_is_tty(stream):
        return
    stream.write(f"\r  {message}")
    stream.flush()


def _clear_prephase_transient_status(*, stream: TextIO) -> None:
    if not _stream_is_tty(stream):
        return
    stream.write("\r\033[K")
    stream.flush()
