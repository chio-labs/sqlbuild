"""Public optional bool entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.authored_values._helpers.fields import optional_bool_impl


def optional_bool(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> bool | None:
    """Extract an optional boolean from a mapping."""

    return optional_bool_impl(
        entry=entry, key=key, file_path=file_path, label=label, error_class=error_class
    )
