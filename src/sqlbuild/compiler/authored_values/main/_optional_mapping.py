"""Public optional mapping entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.authored_values._helpers.fields import optional_mapping_impl


def optional_mapping(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> dict[str, object]:
    """Extract an optional mapping from a mapping, defaulting to empty."""

    return optional_mapping_impl(
        entry=entry, key=key, file_path=file_path, label=label, error_class=error_class
    )
