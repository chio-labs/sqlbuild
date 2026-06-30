"""Public status summary footer formatting entrypoint."""

from __future__ import annotations

from sqlbuild.shared.helpers.cli_style import CliStyle


def format_summary_footer(
    *, counts: tuple[tuple[str, int], ...], use_color: bool, elapsed: str | None = None
) -> str:
    """Format summary counts with semantic colors."""

    style: CliStyle = CliStyle(use_color=use_color)
    parts: list[str] = []
    label: str
    value: int
    success_labels: frozenset[str] = frozenset({"PASS", "OK", "SYNC_PASS", "REFRESH_PASS"})
    warning_labels: frozenset[str] = frozenset({"WARN"})
    error_labels: frozenset[str] = frozenset({"FAIL", "ERROR", "SYNC_FAIL", "REFRESH_FAIL"})
    skip_labels: frozenset[str] = frozenset({"SKIP"})
    for label, value in counts:
        normalized: str = label.upper()
        rendered_value: str = style.value(str(value))
        if normalized in success_labels:
            rendered_value = style.success(str(value))
        elif normalized in warning_labels:
            rendered_value = style.warning(str(value))
        elif normalized in error_labels:
            rendered_value = style.error(str(value))
        elif normalized in skip_labels:
            rendered_value = style.muted(str(value))
        parts.append(f"{style.label(f'{label}=')}{rendered_value}")
    rendered: str = "  ".join(parts)
    if elapsed is not None:
        rendered = f"{rendered}  {style.muted(f'({elapsed})')}"
    return rendered
