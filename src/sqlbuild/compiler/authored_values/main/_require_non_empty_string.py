"""Public require non empty string entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.authored_values._helpers.fields import require_non_empty_string_impl


def require_non_empty_string(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> str:
    """Extract a required non-empty string from a mapping."""

    return require_non_empty_string_impl(
        entry=entry, key=key, file_path=file_path, label=label, error_class=error_class
    )
