"""Public optional named bool entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.authored_values._helpers.fields import optional_named_bool_impl


def optional_named_bool[D: (bool, None)](
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
    default: D,
) -> bool | D:
    """Validate an optional named boolean, returning default when absent."""

    return optional_named_bool_impl(
        raw_value=raw_value,
        file_path=file_path,
        label=label,
        key=key,
        error_class=error_class,
        default=default,
    )
