"""Coded-error rendering implementation."""

from __future__ import annotations

import textwrap

from sqlbuild.presentation.classes.cli_style import CliStyle

_MAX_INLINE_ERROR_LINES: int = 2


def format_coded_error(
    *,
    code: str,
    message: str,
    help: str | None = None,
    use_color: bool = False,
    include_error_label: bool = True,
) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    prefix_text: str = f"error[{code}]:" if include_error_label else f"[{code}]"
    prefix: str = style.error_strong(prefix_text)
    lines: list[str] = message.split("\n")
    rendered_message: str = message
    if len(lines) > 1:
        rendered_message = "\n".join([lines[0], *[style.muted(line) for line in lines[1:]]])
    rendered: str = f"{prefix} {rendered_message}"
    if help is not None:
        help_label: str = style.muted("= help:")
        rendered = f"{rendered}\n  {help_label} {help}"
    return rendered


def format_inline_error_lines(
    *,
    error_code: str | None,
    error_message: str,
    error_help: str | None,
    content_width: int,
    style: CliStyle,
) -> list[str]:
    """Wrap a compact inline diagnostic while preserving semantic code styling."""

    code_prefix: str = f"[{error_code}]" if error_code is not None else ""
    message: str = f"{code_prefix} {error_message}" if code_prefix else error_message
    if error_help is not None:
        message = f"{message}\n= help: {error_help}"
    wrapped_lines: list[str] = []
    paragraph: str
    for paragraph in message.splitlines() or [message]:
        wrapped_lines.extend(
            textwrap.wrap(
                paragraph,
                width=content_width,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    truncated: bool = len(wrapped_lines) > _MAX_INLINE_ERROR_LINES
    visible_lines: list[str] = wrapped_lines[:_MAX_INLINE_ERROR_LINES]
    if truncated:
        final_line: str = visible_lines[-1]
        ellipsis: str = "." * min(3, content_width)
        visible_lines[-1] = (
            f"{final_line[: max(0, content_width - len(ellipsis))].rstrip()}{ellipsis}"
        )
    if code_prefix and visible_lines:
        visible_lines[0] = visible_lines[0].replace(
            code_prefix,
            style.error_strong(code_prefix),
            1,
        )
    return visible_lines
