"""Public optional named string entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.authored_values._helpers.fields import optional_named_string_impl


def optional_named_string(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
) -> str | None:
    """Validate and return an optional named string value."""

    return optional_named_string_impl(
        raw_value=raw_value, file_path=file_path, label=label, key=key, error_class=error_class
    )
