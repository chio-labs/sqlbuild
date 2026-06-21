"""Shared formatting for status summary footers."""

from __future__ import annotations

from sqlbuild.shared.helpers.cli_style import CliStyle

_SUCCESS_LABELS: frozenset[str] = frozenset({"PASS", "OK", "SYNC_PASS", "REFRESH_PASS"})
_WARNING_LABELS: frozenset[str] = frozenset({"WARN"})
_ERROR_LABELS: frozenset[str] = frozenset({"FAIL", "ERROR", "SYNC_FAIL", "REFRESH_FAIL"})
_SKIP_LABELS: frozenset[str] = frozenset({"SKIP"})


def format_summary_footer(
    *, counts: tuple[tuple[str, int], ...], use_color: bool, elapsed: str | None = None
) -> str:
    """Format summary counts with semantic colors."""

    style: CliStyle = CliStyle(use_color=use_color)
    parts: list[str] = []
    label: str
    value: int
    for label, value in counts:
        parts.append(
            f"{style.label(f'{label}=')}{_style_value(style=style, label=label, value=value)}"
        )
    rendered: str = "  ".join(parts)
    if elapsed is not None:
        rendered = f"{rendered}  {style.muted(f'({elapsed})')}"
    return rendered


def _style_value(*, style: CliStyle, label: str, value: int) -> str:
    normalized: str = label.upper()
    if _is_success_label(normalized):
        return style.success(str(value))
    if _is_warning_label(normalized):
        return style.warning(str(value))
    if _is_error_label(normalized):
        return style.error(str(value))
    if _is_skip_label(normalized):
        return style.muted(str(value))
    return style.value(str(value))


def _is_success_label(normalized: str) -> bool:
    return normalized in _SUCCESS_LABELS


def _is_warning_label(normalized: str) -> bool:
    return normalized in _WARNING_LABELS


def _is_error_label(normalized: str) -> bool:
    return normalized in _ERROR_LABELS


def _is_skip_label(normalized: str) -> bool:
    return normalized in _SKIP_LABELS
