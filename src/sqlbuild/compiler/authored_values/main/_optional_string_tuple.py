"""Public optional string tuple entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.authored_values._helpers.fields import optional_string_tuple_impl


def optional_string_tuple(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> tuple[str, ...]:
    """Extract an optional list of strings from a mapping."""

    return optional_string_tuple_impl(
        entry=entry, key=key, file_path=file_path, label=label, error_class=error_class
    )
