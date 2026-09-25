"""Public optional non empty string entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.authored_values._helpers.fields import optional_non_empty_string_impl


def optional_non_empty_string(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> str | None:
    """Extract an optional non-empty string from a mapping."""

    return optional_non_empty_string_impl(
        entry=entry, key=key, file_path=file_path, label=label, error_class=error_class
    )
