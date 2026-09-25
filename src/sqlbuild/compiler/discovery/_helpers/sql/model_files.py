"""Parsing helpers for authored SQL model files."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.exceptions import (
    DiscoveryError,
    ModelHeaderSyntaxError,
    ModelSqlParseError,
)
from sqlbuild.compiler.discovery.models import (
    ModelHeaderColumnSpan,
    NamedSqlHookEntry,
    PythonHookEntry,
    SqlHookEntry,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SourceLocation
from sqlbuild.sql_values.models import AuthoredSqlSet, AuthoredSqlValueCall

_MODEL_HEADER_END_TOKEN: str = "end"
_MODEL_HEADER_WORD_TOKEN: str = "word"
_MODEL_HEADER_STRING_TOKEN: str = "string"
_MODEL_HEADER_SYMBOL_TOKEN: str = "symbol"
_MODEL_HEADER_SYMBOLS: frozenset[str] = frozenset({"(", ")", "[", "]", "{", "}", ","})
_MODEL_HEADER_OPEN_PAREN: str = "("
_MODEL_HEADER_CLOSE_PAREN: str = ")"
_MODEL_HEADER_OPEN_BRACKET: str = "["
_MODEL_HEADER_CLOSE_BRACKET: str = "]"
_MODEL_HEADER_OPEN_BRACE: str = "{"
_MODEL_HEADER_CLOSE_BRACE: str = "}"
_MODEL_HEADER_COMMA: str = ","
_MODEL_HEADER_KEY_VALUE_SEPARATOR: str = ":"
_MODEL_HEADER_QUOTE_NAMES: dict[str, str] = {"'": "single", '"': "double"}
_MODEL_HEADER_ESCAPE_CHARACTER: str = "\\"
_MODEL_HEADER_COLUMNS_KEY: str = "columns"
_MODEL_HEADER_TYPE_KEY: str = "type"
_MODEL_HEADER_RELATION_CALL_NAMES: frozenset[str] = frozenset(
    {
        SqlReferenceKind.REF.function_name,
        SqlReferenceKind.SEED.function_name,
        SqlReferenceKind.SOURCE.function_name,
    }
)
_MODEL_HEADER_INLINE_SQL_HOOK_CALL: str = "inline_sql"
_MODEL_HEADER_NAMED_SQL_HOOK_CALL: str = "sql"
_MODEL_HEADER_PYTHON_HOOK_CALL: str = "python"
_MODEL_HEADER_HOOK_CALL_NAMES: frozenset[str] = frozenset(
    {
        _MODEL_HEADER_INLINE_SQL_HOOK_CALL,
        _MODEL_HEADER_NAMED_SQL_HOOK_CALL,
        _MODEL_HEADER_PYTHON_HOOK_CALL,
    }
)
_MODEL_HEADER_HOOK_FIELD_NAMES: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_MODEL_HEADER_TRUE_VALUE: str = "true"
_MODEL_HEADER_FALSE_VALUE: str = "false"
_MODEL_HEADER_NULL_VALUE: str = "null"
_MODEL_HEADER_TYPED_CONSTANT_CALL: str = "constant"
_MODEL_HEADER_THRESHOLDS_KEY: str = "thresholds"
_MODEL_HEADER_THRESHOLD_BOUND_KEYS: frozenset[str] = frozenset({"warn", "error"})
_SQL_IDENTIFIER_SEPARATOR: str = "_"
_SQL_SELECT_KEYWORD: str = "SELECT"
_SQL_UNION_KEYWORD: str = "UNION"
_SQL_FROM_KEYWORD: str = "FROM"
_SQL_SELECT_INITIAL: str = _SQL_SELECT_KEYWORD[0]
_SQL_UNION_INITIAL: str = _SQL_UNION_KEYWORD[0]
_SQL_FROM_INITIAL: str = _SQL_FROM_KEYWORD[0]
_SQL_UNION_LOWER_KEYWORD: str = _SQL_UNION_KEYWORD.lower()
_MODEL_HEADER_INTEGER_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?\d+$")
_MODEL_HEADER_FLOAT_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)$")
_MODEL_HEADER_TOKEN_CACHE_SIZE: int = 4096
_NATIVE_MODEL_HEADER_END_TOKEN: int = 0
_NATIVE_MODEL_HEADER_WORD_TOKEN: int = 1
_NATIVE_MODEL_HEADER_STRING_TOKEN: int = 2
_NATIVE_MODEL_HEADER_SYMBOL_TOKEN: int = 3
_NATIVE_MARKER_LENGTH: int = 2
_NATIVE_SET_MARKER: str = "set"
_NATIVE_TUPLE_MARKER: str = "tuple"
_NATIVE_CONSTANT_MARKER: str = "constant"
_NATIVE_INLINE_SQL_MARKER: str = "inline_sql"
_NATIVE_SQL_MARKER: str = "sql"
_NATIVE_PYTHON_MARKER: str = "python"
_MODEL_HEADER_TOKEN_KIND_BY_NATIVE: dict[int, str] = {
    _NATIVE_MODEL_HEADER_END_TOKEN: _MODEL_HEADER_END_TOKEN,
    _NATIVE_MODEL_HEADER_WORD_TOKEN: _MODEL_HEADER_WORD_TOKEN,
    _NATIVE_MODEL_HEADER_STRING_TOKEN: _MODEL_HEADER_STRING_TOKEN,
    _NATIVE_MODEL_HEADER_SYMBOL_TOKEN: _MODEL_HEADER_SYMBOL_TOKEN,
}
_MODEL_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*MODEL\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)
_SELECT_SCAN_SPECIAL: re.Pattern[str] = re.compile(r"['\"`()sSfFuU]")


@dataclass(frozen=True)
class _ModelHeaderToken:
    kind: str
    value: str
    position: int


@dataclass(frozen=True)
class _ModelHeaderTokenization:
    values: dict[str, object] | None
    column_relative_locations: tuple[tuple[str, int, int, int], ...] | None
    error: str | None


class _ModelHeaderTokenCache:
    def __init__(self) -> None:
        self._values: OrderedDict[str, _ModelHeaderTokenization] = OrderedDict()

    def missing(self, headers: list[str]) -> list[str]:
        return list(dict.fromkeys(header for header in headers if header not in self._values))

    def get(self, header: str) -> _ModelHeaderTokenization | None:
        tokenization: _ModelHeaderTokenization | None = self._values.get(header)
        if tokenization is not None:
            self._values.move_to_end(header)
        return tokenization

    def put(self, *, header: str, tokenization: _ModelHeaderTokenization) -> None:
        self._values[header] = tokenization
        self._values.move_to_end(header)
        if len(self._values) > _MODEL_HEADER_TOKEN_CACHE_SIZE:
            self._values.popitem(last=False)


_MODEL_HEADER_TOKEN_CACHE: _ModelHeaderTokenCache = _ModelHeaderTokenCache()


def parse_model_sql(*, contents: str, file_path: Path) -> tuple[dict[str, object], str]:
    """Parse a raw SQL model file into header values and SQL body."""

    header_match: re.Match[str] | None = _MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise ModelSqlParseError(
            f"SQL model '{file_path}' must start with a MODEL(...) header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, object] = parse_header_values(
        header=header_match.group("header"),
        file_path=file_path,
        statement_name="MODEL",
    )
    query: str = header_match.group("sql").strip()
    if not query:
        raise ModelSqlParseError(f"SQL model '{file_path}' must contain SQL after MODEL(...)")
    return header_values, query


def model_header_column_locations(
    *, contents: str, relative_path: Path
) -> dict[str, SourceLocation]:
    """Return authored locations for MODEL(columns) declarations."""

    header_match: re.Match[str] | None = _MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        return {}
    return header_column_locations(
        contents=contents,
        header=header_match.group("header"),
        header_start=header_match.start("header"),
        relative_path=relative_path,
    )


def model_header_columns_span(
    *, contents: str
) -> tuple[int, int, dict[str, ModelHeaderColumnSpan]] | None:
    """Return the columns body and column entry spans from the native header tokenizer."""

    header_match: re.Match[str] | None = _MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        return None
    header: str = header_match.group("header")
    header_start: int = header_match.start("header")
    tokens: list[_ModelHeaderToken] = _tokenize_model_header_for_spans(header)
    columns_open_index: int | None = None
    depth: int = 0
    for index, token in enumerate(tokens):
        if (
            token.kind == _MODEL_HEADER_WORD_TOKEN
            and token.value == _MODEL_HEADER_COLUMNS_KEY
            and depth == 0
            and tokens[index + 1].value == _MODEL_HEADER_OPEN_PAREN
        ):
            columns_open_index = index + 1
            break
        if token.kind == _MODEL_HEADER_SYMBOL_TOKEN and token.value == _MODEL_HEADER_OPEN_PAREN:
            depth += 1
        elif token.kind == _MODEL_HEADER_SYMBOL_TOKEN and token.value == _MODEL_HEADER_CLOSE_PAREN:
            depth -= 1
    if columns_open_index is None:
        return None
    open_token: _ModelHeaderToken = tokens[columns_open_index]
    spans: dict[str, ModelHeaderColumnSpan] = {}
    depth = 1
    index: int = columns_open_index + 1
    close_token: _ModelHeaderToken | None = None
    while index < len(tokens):
        token: _ModelHeaderToken = tokens[index]
        if token.kind == _MODEL_HEADER_SYMBOL_TOKEN and token.value == _MODEL_HEADER_OPEN_PAREN:
            depth += 1
        elif token.kind == _MODEL_HEADER_SYMBOL_TOKEN and token.value == _MODEL_HEADER_CLOSE_PAREN:
            depth -= 1
            if depth == 0:
                close_token = token
                break
        elif token.kind == _MODEL_HEADER_WORD_TOKEN and depth == 1:
            metadata_open: _ModelHeaderToken = tokens[index + 1]
            if metadata_open.value == _MODEL_HEADER_OPEN_PAREN:
                metadata_depth: int = 1
                end_index: int = index + 2
                while end_index < len(tokens):
                    candidate: _ModelHeaderToken = tokens[end_index]
                    if candidate.value == _MODEL_HEADER_OPEN_PAREN:
                        metadata_depth += 1
                    elif candidate.value == _MODEL_HEADER_CLOSE_PAREN:
                        metadata_depth -= 1
                        if metadata_depth == 0:
                            spans[token.value] = ModelHeaderColumnSpan(
                                entry_start=header_start + token.position,
                                entry_end=header_start + candidate.position + 1,
                                metadata_start=header_start + metadata_open.position + 1,
                                metadata_end=header_start + candidate.position,
                            )
                            index = end_index
                            break
                    end_index += 1
        index += 1
    if close_token is None:
        return None
    return (
        header_start + open_token.position + 1,
        header_start + close_token.position,
        spans,
    )


def model_header_body_span(*, contents: str) -> tuple[int, int] | None:
    """Return authored byte offsets for the MODEL header body."""

    header_match: re.Match[str] | None = _MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        return None
    return header_match.start("header"), header_match.end("header")


def header_column_locations(
    *, contents: str, header: str, header_start: int, relative_path: Path
) -> dict[str, SourceLocation]:
    """Return authored column locations from a parsed SQLBuild header."""

    tokenization: _ModelHeaderTokenization = _model_header_parse(header)
    if tokenization.column_relative_locations is None:
        raise ModelHeaderSyntaxError("Native MODEL header parser returned no column locations")
    header_line: int = contents.count("\n", 0, header_start) + 1
    preceding_newline: int = contents.rfind("\n", 0, header_start)
    header_column: int = (
        header_start + 1 if preceding_newline < 0 else header_start - preceding_newline
    )
    return {
        name: SourceLocation(
            path=relative_path,
            line=header_line + relative_line - 1,
            column=relative_column + (header_column - 1 if relative_line == 1 else 0),
            end_line=header_line + relative_line - 1,
            end_column=(
                relative_column + (header_column - 1 if relative_line == 1 else 0) + length
            ),
        )
        for name, relative_line, relative_column, length in tokenization.column_relative_locations
    }


def model_output_column_locations(
    *, contents: str, relative_path: Path, extract_implicit_alias_columns: bool = True
) -> dict[str, SourceLocation]:
    """Return authored locations for simple SELECT output expressions."""

    header_match: re.Match[str] | None = _MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        return {}
    sql_start: int = header_match.start("sql")
    sql: str = header_match.group("sql")
    projection_ranges: tuple[tuple[int, int], ...] | None = _top_level_select_projection_ranges(sql)
    if projection_ranges is None:
        return {}
    return _scanner_output_column_locations(
        contents=contents,
        sql_start=sql_start,
        relative_path=relative_path,
        projection_ranges=projection_ranges,
        extract_implicit_alias_columns=extract_implicit_alias_columns,
        line_starts=_line_starts(contents),
    )


def _top_level_select_projection_ranges(sql: str) -> tuple[tuple[int, int], ...] | None:
    bounds: tuple[int, int] | None = _top_level_select_list_bounds(sql)
    if bounds is None:
        return None
    select_list_start, select_list_end = bounds
    return _split_top_level_select_items(sql=sql, start=select_list_start, end=select_list_end)


def _top_level_select_list_bounds(sql: str) -> tuple[int, int] | None:
    depth: int = 0
    index: int = 0
    select_list_start: int | None = None
    select_list_end: int | None = None
    in_quote: str | None = None
    length: int = len(sql)
    has_union_candidate: bool = _SQL_UNION_LOWER_KEYWORD in sql.lower()
    while index < length:
        if in_quote is None:
            special: re.Match[str] | None = _SELECT_SCAN_SPECIAL.search(sql, index)
            if special is None:
                break
            index = special.start()
        character: str = sql[index]
        if in_quote is not None:
            if character == _MODEL_HEADER_ESCAPE_CHARACTER:
                index += 2
                continue
            if character == in_quote:
                in_quote = None
            index += 1
            continue
        if character in _MODEL_HEADER_QUOTE_NAMES:
            in_quote = character
            index += 1
            continue
        if character == _MODEL_HEADER_OPEN_PAREN:
            depth += 1
            index += 1
            continue
        if character == _MODEL_HEADER_CLOSE_PAREN:
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth != 0:
            index += 1
            continue
        upper_character: str = character.upper()
        if select_list_start is None:
            if upper_character == _SQL_SELECT_INITIAL and _keyword_at(
                sql=sql, keyword=_SQL_SELECT_KEYWORD, index=index
            ):
                select_list_start = index + len(_SQL_SELECT_KEYWORD)
                index = select_list_start
                continue
        else:
            if upper_character == _SQL_UNION_INITIAL and _keyword_at(
                sql=sql, keyword=_SQL_UNION_KEYWORD, index=index
            ):
                return None
            if (
                select_list_end is None
                and upper_character == _SQL_FROM_INITIAL
                and _keyword_at(sql=sql, keyword=_SQL_FROM_KEYWORD, index=index)
            ):
                select_list_end = index
                if not has_union_candidate:
                    return select_list_start, select_list_end
        index += 1
    if select_list_start is None:
        return None
    return select_list_start, select_list_end if select_list_end is not None else length


def _scanner_output_column_locations(
    *,
    contents: str,
    sql_start: int,
    relative_path: Path,
    projection_ranges: tuple[tuple[int, int], ...],
    extract_implicit_alias_columns: bool,
    line_starts: tuple[int, ...],
) -> dict[str, SourceLocation]:
    locations: dict[str, SourceLocation] = {}
    item_start: int
    item_end: int
    for item_start, item_end in projection_ranges:
        output_name: str | None = _select_item_output_name(
            item=contents[sql_start + item_start : sql_start + item_end],
            extract_implicit_alias_columns=extract_implicit_alias_columns,
        )
        if output_name is None:
            continue
        location: SourceLocation | None = _location_for_projection_range(
            contents=contents,
            sql_start=sql_start,
            relative_path=relative_path,
            projection_range=(item_start, item_end),
            line_starts=line_starts,
        )
        if location is not None:
            locations[output_name] = location
    return locations


def _location_for_projection_range(
    *,
    contents: str,
    sql_start: int,
    relative_path: Path,
    projection_range: tuple[int, int],
    line_starts: tuple[int, ...],
) -> SourceLocation | None:
    item_start: int = projection_range[0]
    item_end: int = projection_range[1]
    sql: str = contents[sql_start:]
    start_offset: int = _skip_local_whitespace(sql=sql, start=item_start, end=item_end)
    end_offset: int = _trim_local_whitespace(sql=sql, start=start_offset, end=item_end)
    if start_offset >= end_offset:
        return None
    return _location_for_absolute_span(
        contents=contents,
        start=sql_start + start_offset,
        end=sql_start + end_offset,
        relative_path=relative_path,
        line_starts=line_starts,
    )


def _location_for_absolute_span(
    *, contents: str, start: int, end: int, relative_path: Path, line_starts: tuple[int, ...]
) -> SourceLocation:
    end = max(start, end)
    end_position: int = max(start, end - 1)
    line_index: int = bisect_right(line_starts, start) - 1
    line: int = line_index + 1
    line_start: int = line_starts[line_index]
    column: int = start - line_start + 1
    end_line_index: int = bisect_right(line_starts, end_position) - 1
    end_line: int = end_line_index + 1
    end_line_start: int = line_starts[end_line_index]
    end_column: int = end_position - end_line_start + 2
    return SourceLocation(
        path=relative_path,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
    )


def _line_starts(contents: str) -> tuple[int, ...]:
    starts: list[int] = [0]
    index: int = contents.find("\n")
    while index != -1:
        starts.append(index + 1)
        index = contents.find("\n", index + 1)
    return tuple(starts)


def _split_top_level_select_items(*, sql: str, start: int, end: int) -> tuple[tuple[int, int], ...]:
    items: list[tuple[int, int]] = []
    depth: int = 0
    item_start: int = start
    index: int = start
    in_quote: str | None = None
    while index < end:
        character: str = sql[index]
        if in_quote is not None:
            if character == _MODEL_HEADER_ESCAPE_CHARACTER:
                index += 2
                continue
            if character == in_quote:
                in_quote = None
            index += 1
            continue
        if character in _MODEL_HEADER_QUOTE_NAMES:
            in_quote = character
            index += 1
            continue
        if character == _MODEL_HEADER_OPEN_PAREN:
            depth += 1
        elif character == _MODEL_HEADER_CLOSE_PAREN:
            depth = max(0, depth - 1)
        elif character == _MODEL_HEADER_COMMA and depth == 0:
            items.append((item_start, index))
            item_start = index + 1
        index += 1
    items.append((item_start, end))
    return tuple(items)


def _select_item_output_name(*, item: str, extract_implicit_alias_columns: bool) -> str | None:
    as_match: re.Match[str] | None = re.search(
        r"\s+AS\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")\s*\Z",
        item,
        flags=re.IGNORECASE,
    )
    if as_match is not None:
        return as_match.group("name").strip('"')
    bare_match: re.Match[str] | None = re.match(
        r"\s*(?:(?:[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")\.)?"
        r"(?P<name>[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")\s*\Z",
        item,
    )
    if bare_match is None:
        if not extract_implicit_alias_columns:
            return None
        implicit_alias_match: re.Match[str] | None = re.search(
            r"\)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")\s*\Z",
            item,
        )
        if implicit_alias_match is None:
            return None
        return implicit_alias_match.group("name").strip('"')
    return bare_match.group("name").strip('"')


def _skip_local_whitespace(*, sql: str, start: int, end: int) -> int:
    while start < end and sql[start].isspace():
        start += 1
    return start


def _trim_local_whitespace(*, sql: str, start: int, end: int) -> int:
    while end > start and sql[end - 1].isspace():
        end -= 1
    return end


def _keyword_at(*, sql: str, keyword: str, index: int) -> bool:
    end: int = index + len(keyword)
    if sql[index:end].upper() != keyword:
        return False
    before: str = sql[index - 1] if index > 0 else " "
    after: str = sql[end] if end < len(sql) else " "
    return not (before.isalnum() or before == _SQL_IDENTIFIER_SEPARATOR) and not (
        after.isalnum() or after == _SQL_IDENTIFIER_SEPARATOR
    )


def parse_header_values(
    *,
    header: str,
    file_path: Path,
    statement_name: str,
    error_class: type[DiscoveryError] = ModelSqlParseError,
) -> dict[str, object]:
    """Parse one SQLBuild parenthesized header into nested Python values."""

    try:
        parsed: _ModelHeaderTokenization = _model_header_parse(header)
        if parsed.values is None:
            raise ModelHeaderSyntaxError(
                "Native MODEL header parser returned neither values nor an error"
            )
        return dict(parsed.values)
    except ModelSqlParseError:
        raise
    except ModelHeaderSyntaxError as error:
        raise error_class(
            f"{statement_name}(...) in '{file_path}' contains invalid SQLBuild header syntax: "
            f"{error}"
        ) from error


def prepare_model_header_tokens(headers: list[str]) -> None:
    """Batch cache-missing MODEL header semantic parsing through the native parser."""

    missing_headers: list[str] = _MODEL_HEADER_TOKEN_CACHE.missing(headers)
    if not missing_headers:
        return
    tokenizations: list[
        tuple[
            dict[str, object] | None,
            list[tuple[str, int, int]] | None,
            str | None,
        ]
    ] = _native.parse_model_headers(missing_headers)
    if len(tokenizations) != len(missing_headers):
        raise ModelHeaderSyntaxError("Native MODEL header tokenizer returned an incomplete batch")
    for header, (native_values, column_offsets, error) in zip(
        missing_headers, tokenizations, strict=True
    ):
        _cache_model_header_tokenization(
            header=header,
            tokenization=_ModelHeaderTokenization(
                values=(
                    _project_native_header_map(native_values) if native_values is not None else None
                ),
                column_relative_locations=(
                    _header_column_relative_locations(header=header, offsets=column_offsets)
                    if column_offsets is not None
                    else None
                ),
                error=error,
            ),
        )


def _header_column_relative_locations(
    *, header: str, offsets: list[tuple[str, int, int]]
) -> tuple[tuple[str, int, int, int], ...]:
    """Project ordered header offsets to one-based relative source locations in one pass."""

    locations: list[tuple[str, int, int, int]] = []
    line: int = 1
    column: int = 1
    cursor: int = 0
    for name, position, length in offsets:
        while cursor < position:
            newline: int = header.find("\n", cursor, position)
            if newline < 0:
                column += position - cursor
                cursor = position
            else:
                line += 1
                column = 1
                cursor = newline + 1
        locations.append((name, line, column, length))
    return tuple(locations)


def prepare_model_file_headers(contents: list[str]) -> None:
    """Batch tokenization for syntactically recognizable MODEL file headers."""

    prepare_model_header_tokens(
        [
            header_match.group("header")
            for contents_value in contents
            if (header_match := _MODEL_HEADER_PATTERN.match(contents_value)) is not None
        ]
    )


def _project_native_header_map(values: dict[str, object]) -> dict[str, object]:
    return {key: _project_native_header_value(value) for key, value in values.items()}


def _project_native_header_value(value: object) -> object:
    if isinstance(value, dict):
        return _project_native_header_map(cast(dict[str, object], value))
    if isinstance(value, list):
        return [_project_native_header_value(item) for item in value]
    if (
        not isinstance(value, tuple)
        or len(value) != _NATIVE_MARKER_LENGTH
        or not isinstance(value[0], str)
    ):
        return value
    kind: str = value[0]
    payload: object = value[1]
    if kind == _MODEL_HEADER_WORD_TOKEN and isinstance(payload, str):
        return _parse_word_value(payload)
    if kind == _NATIVE_SET_MARKER and isinstance(payload, list):
        return AuthoredSqlSet(tuple(_project_native_header_value(item) for item in payload))
    if kind == _NATIVE_TUPLE_MARKER and isinstance(payload, list):
        return tuple(_project_native_header_value(item) for item in payload)
    if kind == _NATIVE_CONSTANT_MARKER and isinstance(payload, dict):
        return AuthoredSqlValueCall(
            arguments=tuple(_project_native_header_map(cast(dict[str, object], payload)).items())
        )
    if kind == _NATIVE_INLINE_SQL_MARKER and isinstance(payload, str):
        return SqlHookEntry(statement=payload)
    if (
        kind in {_NATIVE_SQL_MARKER, _NATIVE_PYTHON_MARKER}
        and isinstance(payload, tuple)
        and len(payload) == _NATIVE_MARKER_LENGTH
    ):
        name, kwargs = payload
        if isinstance(name, str) and isinstance(kwargs, dict):
            projected_kwargs: dict[str, object] = _project_native_header_map(
                cast(dict[str, object], kwargs)
            )
            if kind == _NATIVE_SQL_MARKER:
                return NamedSqlHookEntry(name=name, kwargs=projected_kwargs)
            return PythonHookEntry(name=name, kwargs=projected_kwargs)
    raise ModelHeaderSyntaxError(f"Native MODEL header parser returned invalid '{kind}' marker")


def _model_header_parse(header: str) -> _ModelHeaderTokenization:
    tokenization: _ModelHeaderTokenization | None = _MODEL_HEADER_TOKEN_CACHE.get(header)
    if tokenization is None:
        prepare_model_header_tokens([header])
        tokenization = _MODEL_HEADER_TOKEN_CACHE.get(header)
        if tokenization is None:
            raise ModelHeaderSyntaxError("Native MODEL header parser did not populate its cache")
    if tokenization.error is not None:
        raise ModelHeaderSyntaxError(tokenization.error)
    return tokenization


def _tokenize_model_header_for_spans(header: str) -> list[_ModelHeaderToken]:
    return [
        _ModelHeaderToken(
            kind=_MODEL_HEADER_TOKEN_KIND_BY_NATIVE[kind],
            value=value,
            position=position,
        )
        for kind, value, position in _native.tokenize_model_header(header)
    ]


def _cache_model_header_tokenization(
    *, header: str, tokenization: _ModelHeaderTokenization
) -> None:
    _MODEL_HEADER_TOKEN_CACHE.put(header=header, tokenization=tokenization)


def _parse_word_value(value: str) -> object:
    if value == _MODEL_HEADER_TRUE_VALUE:
        return True
    if value == _MODEL_HEADER_FALSE_VALUE:
        return False
    if value == _MODEL_HEADER_NULL_VALUE:
        return None
    if _MODEL_HEADER_INTEGER_PATTERN.match(value):
        return int(value)
    if _MODEL_HEADER_FLOAT_PATTERN.match(value):
        return float(value)
    return value
