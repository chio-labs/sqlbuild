"""Public access to authored model output-column locations."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    model_output_column_locations,
)
from sqlbuild.spec.contracts.models import SourceLocation


def extract_model_output_column_locations(
    *,
    contents: str,
    relative_path: Path,
    extract_implicit_alias_columns: bool,
) -> dict[str, SourceLocation]:
    """Locate authored output projections only when a compiler consumer needs them."""

    return model_output_column_locations(
        contents=contents,
        relative_path=relative_path,
        extract_implicit_alias_columns=extract_implicit_alias_columns,
    )
