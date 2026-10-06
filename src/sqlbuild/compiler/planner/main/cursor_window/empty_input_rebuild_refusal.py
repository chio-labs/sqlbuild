"""Public wording for refusing to rebuild an existing table from empty cursor inputs."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    empty_input_rebuild_refusal as _empty_input_rebuild_refusal,
)


def empty_input_rebuild_refusal(
    *, model_name: str, input_names: tuple[str, ...], cursor_type: str | None
) -> tuple[str, str]:
    """Return the message and help for refusing to rebuild an existing table from empty inputs."""

    return _empty_input_rebuild_refusal(
        model_name=model_name, input_names=input_names, cursor_type=cursor_type
    )
