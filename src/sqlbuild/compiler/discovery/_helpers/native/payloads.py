"""Shared decoding of the plain-data payloads native discovery returns."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.exceptions import DiscoveryError, ModelSqlParseError
from sqlbuild.compiler.discovery.types import NativeLocation
from sqlbuild.spec.contracts.models import SourceLocation

_DISPLAY_PROBE: str = "_"
_FAILURE_CLASSES: dict[str, type[DiscoveryError]] = {"model_sql": ModelSqlParseError}


def native_display_prefix(project_dir: Path) -> str:
    """Return the text `str(project_dir / name)` prints before `name`."""

    return str(project_dir / _DISPLAY_PROBE)[: -len(_DISPLAY_PROBE)]


def native_failure(payload: tuple[object, ...]) -> DiscoveryError:
    """Build the discovery error a native failure payload describes."""

    _tag, kind, message, help_text = payload
    error_class: type[DiscoveryError] = _FAILURE_CLASSES[str(kind)]
    return error_class(str(message), help=None if help_text is None else str(help_text))


def native_locations(
    *, locations: list[NativeLocation], relative_path: Path
) -> dict[str, SourceLocation]:
    """Build authored locations; a repeated name keeps its first position and last value."""

    return {
        name: SourceLocation(
            path=relative_path,
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
        )
        for name, line, column, end_line, end_column in locations
    }
