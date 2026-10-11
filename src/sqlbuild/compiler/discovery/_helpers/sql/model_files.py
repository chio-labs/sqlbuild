"""Native MODEL header parsing and authored-location queries for SQL model files."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.exceptions import (
    DiscoveryError,
    ModelHeaderSyntaxError,
    ModelSqlParseError,
)
from sqlbuild.spec.contracts.models import SourceLocation

_MODEL_HEADER_TOKEN_CACHE_SIZE: int = 4096


@dataclass(frozen=True)
class _ModelHeaderParse:
    values: dict[str, object] | None
    error: str | None


class _ModelHeaderParseCache:
    def __init__(self) -> None:
        self._values: OrderedDict[str, _ModelHeaderParse] = OrderedDict()

    def missing(self, headers: list[str]) -> list[str]:
        return list(dict.fromkeys(header for header in headers if header not in self._values))

    def get(self, header: str) -> _ModelHeaderParse | None:
        parsed: _ModelHeaderParse | None = self._values.get(header)
        if parsed is not None:
            self._values.move_to_end(header)
        return parsed

    def put(self, *, header: str, parsed: _ModelHeaderParse) -> None:
        self._values[header] = parsed
        self._values.move_to_end(header)
        if len(self._values) > _MODEL_HEADER_TOKEN_CACHE_SIZE:
            self._values.popitem(last=False)


_MODEL_HEADER_PARSE_CACHE: _ModelHeaderParseCache = _ModelHeaderParseCache()


def header_column_locations(
    *, contents: str, header: str, header_start: int, relative_path: Path
) -> dict[str, SourceLocation]:
    """Return authored column locations from a parsed SQLBuild header."""

    locations, error = _native.model_header_column_locations(contents, header, header_start)
    if locations is None:
        raise ModelHeaderSyntaxError(str(error))
    return _source_locations(rows=locations, relative_path=relative_path)


def model_output_column_locations(
    *, contents: str, relative_path: Path, extract_implicit_alias_columns: bool = True
) -> dict[str, SourceLocation]:
    """Return authored locations for simple SELECT output expressions."""

    return _source_locations(
        rows=_native.model_output_columns(contents, extract_implicit_alias_columns),
        relative_path=relative_path,
    )


def _source_locations(
    *, rows: list[tuple[str, int, int, int, int]], relative_path: Path
) -> dict[str, SourceLocation]:
    return {
        name: SourceLocation(
            path=relative_path, line=line, column=column, end_line=end_line, end_column=end_column
        )
        for name, line, column, end_line, end_column in rows
    }


def parse_header_values(
    *,
    header: str,
    file_path: Path,
    statement_name: str,
    header_line: int | None,
    error_class: type[DiscoveryError] = ModelSqlParseError,
) -> dict[str, object]:
    """Parse one header; a nesting error names its file line when `header_line` is known."""

    parsed: _ModelHeaderParse = _model_header_parse(header)
    if parsed.values is not None:
        return dict(parsed.values)
    error: ModelHeaderSyntaxError = ModelHeaderSyntaxError(str(parsed.error))
    detail, help_text, line = _native.model_header_failure(str(parsed.error), header, header_line)
    location: str = str(file_path) if line is None else f"{file_path}:{line}"
    raise error_class(
        f"{statement_name}(...) in '{location}' contains invalid SQLBuild header syntax: {detail}",
        help=help_text,
    ) from error


def prepare_model_header_tokens(headers: list[str]) -> None:
    """Batch cache-missing MODEL header semantic parsing through the native parser."""

    missing_headers: list[str] = _MODEL_HEADER_PARSE_CACHE.missing(headers)
    if not missing_headers:
        return
    parsed_headers: list[
        tuple[dict[str, object] | None, list[tuple[str, int, int]] | None, str | None]
    ] = _native.parse_model_headers(missing_headers)
    for header, (values, _offsets, error) in zip(missing_headers, parsed_headers, strict=True):
        _MODEL_HEADER_PARSE_CACHE.put(
            header=header, parsed=_ModelHeaderParse(values=values, error=error)
        )


def _model_header_parse(header: str) -> _ModelHeaderParse:
    parsed: _ModelHeaderParse | None = _MODEL_HEADER_PARSE_CACHE.get(header)
    if parsed is None:
        prepare_model_header_tokens([header])
        parsed = _MODEL_HEADER_PARSE_CACHE.get(header)
    if parsed is None:
        raise ModelHeaderSyntaxError("Native MODEL header parser did not populate its cache")
    return parsed
