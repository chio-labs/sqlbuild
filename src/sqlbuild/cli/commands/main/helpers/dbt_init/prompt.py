"""Interactive setup helpers for `sqb dbt init`."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.shared.helpers.cli_style import CliStyle


def resolve_production_git_ref(
    *,
    explicit_git_ref: str | None,
    input_stream: TextIO,
    output_stream: TextIO,
    use_color: bool,
) -> str:
    """Return the production-shaped git ref to write into dbt reuse config."""

    if explicit_git_ref is not None and explicit_git_ref.strip():
        return explicit_git_ref.strip()
    default_ref: str = "main"
    if not input_stream.isatty():
        return default_ref
    style: CliStyle = CliStyle(use_color=use_color)
    output_stream.write(
        "\n"
        + style.title("dbt production reuse setup")
        + "\n"
        + "SQLBuild can reuse already-built dbt tables from your production-shaped git ref.\n"
        + "Enter the branch or tag that represents production.\n\n"
    )
    output_stream.write(f"Production git ref [{default_ref}]: ")
    output_stream.flush()
    response: str = input_stream.readline().strip()
    if response:
        return response
    return default_ref
