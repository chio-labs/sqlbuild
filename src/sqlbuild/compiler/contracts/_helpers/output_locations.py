"""Source locations of a model's output columns, for contract diagnostics."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledModel, RelatedLocation
from sqlbuild.compiler.discovery.main._model_output_column_locations import (
    extract_model_output_column_locations,
)
from sqlbuild.spec.contracts.models import SourceLocation


def output_related_locations(
    *, model: CompiledModel, column_name: str, message: str
) -> tuple[RelatedLocation, ...]:
    """The output column's location as a related location, when the model has one."""

    location: SourceLocation | None = output_column_location(model=model, column_name=column_name)
    if location is None:
        return ()
    return (RelatedLocation(label="output", location=location, message=message),)


def output_column_location(*, model: CompiledModel, column_name: str) -> SourceLocation | None:
    """Where the model's SQL produces one output column."""

    location: SourceLocation | None = model.output_column_locations.get(column_name)
    if location is not None or not model.authored_sql:
        return location
    return dict(
        _lazy_output_column_locations(
            contents=model.authored_sql,
            relative_path=model.relative_path,
            extract_implicit_alias_columns=model.extract_implicit_alias_columns,
        )
    ).get(column_name)


@lru_cache(maxsize=256)
def _lazy_output_column_locations(
    *, contents: str, relative_path: Path, extract_implicit_alias_columns: bool
) -> tuple[tuple[str, SourceLocation], ...]:
    return tuple(
        extract_model_output_column_locations(
            contents=contents,
            relative_path=relative_path,
            extract_implicit_alias_columns=extract_implicit_alias_columns,
        ).items()
    )
