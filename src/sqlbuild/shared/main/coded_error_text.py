"""Public coded-error formatting entrypoint."""

from __future__ import annotations

from sqlbuild.shared.helpers.output.cli_style import CliStyle


def format_coded_error(
    *, code: str, message: str, help: str | None = None, use_color: bool = False
) -> str:
    """Render a result-stored coded error consistently with CLI expected errors."""

    style: CliStyle = CliStyle(use_color=use_color)
    prefix: str = style.error_strong(f"error[{code}]:")
    lines: list[str] = message.split("\n")
    rendered_message: str = message
    if len(lines) > 1:
        rendered_message = "\n".join([lines[0], *[style.muted(line) for line in lines[1:]]])
    rendered: str = f"{prefix} {rendered_message}"
    if help is not None:
        help_label: str = style.muted("= help:")
        rendered = f"{rendered}\n  {help_label} {help}"
    return rendered
