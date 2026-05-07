"""Parsing helpers for authored SQL model files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.exceptions import ModelSqlParseError
from sqlbuild.compiler.discovery.helpers.constants import MODEL_HEADER_PATTERN
from sqlbuild.shared.helpers.sqlglot import import_sqlglot
from sqlbuild.spec.models.schema import SourceLocation


@dataclass(frozen=True)
class _ModelHeaderToken:
    kind: str
    value: str
    position: int


_END_TOKEN: str = "end"
_WORD_TOKEN: str = "word"
_STRING_TOKEN: str = "string"
_SYMBOL_TOKEN: str = "symbol"
_SYMBOLS: frozenset[str] = frozenset({"(", ")", "[", "]", ","})
_QUOTE_NAMES: dict[str, str] = {"'": "single", '"': "double"}
_INTEGER_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?\d+$")
_FLOAT_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)$")
_RELATION_CALL_NAMES: frozenset[str] = frozenset({"__ref", "__seed", "__source"})


def parse_model_sql(contents: str, file_path: Path) -> tuple[dict[str, object], str]:
    """Parse a raw SQL model file into header values and SQL body."""

    header_match: re.Match[str] | None = MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise ModelSqlParseError(
            f"SQL model '{file_path}' must start with a MODEL(...) header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, object] = _parse_model_header(
        header=header_match.group("header"),
        file_path=file_path,
    )
    query: str = header_match.group("sql").strip()
    if not query:
        raise ModelSqlParseError(f"SQL model '{file_path}' must contain SQL after MODEL(...)")
    return header_values, query


def model_header_column_locations(
    *, contents: str, relative_path: Path
) -> dict[str, SourceLocation]:
    """Return authored locations for MODEL(columns) declarations."""

    header_match: re.Match[str] | None = MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        return {}
    header: str = header_match.group("header")
    header_start: int = header_match.start("header")
    tokens: list[_ModelHeaderToken] = _tokenize_model_header(header)
    locations: dict[str, SourceLocation] = {}
    depth: int = 0
    in_columns: bool = False
    token_index: int = 0
    while token_index < len(tokens):
        token: _ModelHeaderToken = tokens[token_index]
        if token.kind == _END_TOKEN:
            break
        if token.kind == _WORD_TOKEN and token.value == "columns" and depth == 0:
            next_token: _ModelHeaderToken = tokens[token_index + 1]
            if next_token.kind == _SYMBOL_TOKEN and next_token.value == "(":
                in_columns = True
        elif in_columns and token.kind == _WORD_TOKEN and depth == 1:
            locations[token.value] = _location_for_header_token(
                contents=contents,
                header_start=header_start,
                token=token,
                relative_path=relative_path,
            )
        if token.kind == _SYMBOL_TOKEN and token.value == "(":
            depth += 1
        elif token.kind == _SYMBOL_TOKEN and token.value == ")":
            depth -= 1
            if in_columns and depth == 0:
                break
        token_index += 1
    return locations


def model_output_column_locations(
    *, contents: str, relative_path: Path, sqlglot_enabled: bool = True
) -> dict[str, SourceLocation]:
    """Return authored locations for simple SELECT output expressions."""

    header_match: re.Match[str] | None = MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        return {}
    sql_start: int = header_match.start("sql")
    sql: str = header_match.group("sql")
    sqlglot_output_names: tuple[str | None, ...] | None = (
        _sqlglot_projection_output_names(sql) if sqlglot_enabled else None
    )
    if sqlglot_output_names == ():
        return {}
    projection_ranges: tuple[tuple[int, int], ...] | None = _top_level_select_projection_ranges(sql)
    if projection_ranges is None:
        return {}
    if sqlglot_output_names is not None:
        if len(sqlglot_output_names) != len(projection_ranges):
            return {}
        return _locations_from_projection_names(
            contents=contents,
            sql_start=sql_start,
            relative_path=relative_path,
            projection_ranges=projection_ranges,
            output_names=sqlglot_output_names,
        )
    return _scanner_output_column_locations(
        contents=contents,
        sql_start=sql_start,
        relative_path=relative_path,
        projection_ranges=projection_ranges,
    )


def _top_level_select_projection_ranges(sql: str) -> tuple[tuple[int, int], ...] | None:
    select_start: int | None = _find_top_level_keyword(sql, "SELECT", start=0)
    if select_start is None:
        return None
    select_list_start: int = select_start + len("SELECT")
    if _find_top_level_keyword(sql, "UNION", start=select_list_start) is not None:
        return None
    from_start: int | None = _find_top_level_keyword(sql, "FROM", start=select_list_start)
    select_list_end: int = from_start if from_start is not None else len(sql)
    return _split_top_level_select_items(sql, start=select_list_start, end=select_list_end)


def _scanner_output_column_locations(
    *,
    contents: str,
    sql_start: int,
    relative_path: Path,
    projection_ranges: tuple[tuple[int, int], ...],
) -> dict[str, SourceLocation]:
    locations: dict[str, SourceLocation] = {}
    item_start: int
    item_end: int
    for item_start, item_end in projection_ranges:
        output_name: str | None = _select_item_output_name(
            contents[sql_start + item_start : sql_start + item_end]
        )
        if output_name is None:
            continue
        location: SourceLocation | None = _location_for_projection_range(
            contents=contents,
            sql_start=sql_start,
            relative_path=relative_path,
            projection_range=(item_start, item_end),
        )
        if location is not None:
            locations[output_name] = location
    return locations


def _locations_from_projection_names(
    *,
    contents: str,
    sql_start: int,
    relative_path: Path,
    projection_ranges: tuple[tuple[int, int], ...],
    output_names: tuple[str | None, ...],
) -> dict[str, SourceLocation]:
    locations: dict[str, SourceLocation] = {}
    for output_name, projection_range in zip(output_names, projection_ranges, strict=True):
        if output_name is None or output_name == "*":
            continue
        location: SourceLocation | None = _location_for_projection_range(
            contents=contents,
            sql_start=sql_start,
            relative_path=relative_path,
            projection_range=projection_range,
        )
        if location is not None:
            locations[output_name] = location
    return locations


def _location_for_projection_range(
    *, contents: str, sql_start: int, relative_path: Path, projection_range: tuple[int, int]
) -> SourceLocation | None:
    item_start: int = projection_range[0]
    item_end: int = projection_range[1]
    sql: str = contents[sql_start:]
    start_offset: int = _skip_local_whitespace(sql, item_start, item_end)
    end_offset: int = _trim_local_whitespace(sql, start_offset, item_end)
    if start_offset >= end_offset:
        return None
    return _location_for_absolute_span(
        contents=contents,
        start=sql_start + start_offset,
        end=sql_start + end_offset,
        relative_path=relative_path,
    )


def _sqlglot_projection_output_names(sql: str) -> tuple[str | None, ...] | None:
    sqlglot_module: Any | None = import_sqlglot()
    if sqlglot_module is None:
        return None
    try:
        parsed: Any = sqlglot_module.parse_one(sql)
    except Exception:
        return None
    if type(parsed).__name__ != "Select":
        return ()
    output_names: list[str | None] = []
    projection: Any
    for projection in parsed.expressions:
        if "Star" in type(projection).__name__:
            output_names.append(None)
            continue
        raw_name: object | None = getattr(projection, "alias_or_name", None)
        if raw_name is None:
            output_names.append(None)
            continue
        output_name: str = str(raw_name)
        output_names.append(output_name if output_name and output_name != "*" else None)
    return tuple(output_names)


def _location_for_header_token(
    *, contents: str, header_start: int, token: _ModelHeaderToken, relative_path: Path
) -> SourceLocation:
    absolute_position: int = header_start + token.position
    return _location_for_absolute_span(
        contents=contents,
        start=absolute_position,
        end=absolute_position + len(token.value),
        relative_path=relative_path,
    )


def _location_for_absolute_span(
    *, contents: str, start: int, end: int, relative_path: Path
) -> SourceLocation:
    end = max(start, end)
    end_position: int = max(start, end - 1)
    line: int = contents.count("\n", 0, start) + 1
    line_start: int = contents.rfind("\n", 0, start) + 1
    column: int = start - line_start + 1
    end_line: int = contents.count("\n", 0, end_position) + 1
    end_line_start: int = contents.rfind("\n", 0, end_position) + 1
    end_column: int = end_position - end_line_start + 2
    return SourceLocation(
        path=relative_path,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
    )


def _find_top_level_keyword(sql: str, keyword: str, *, start: int) -> int | None:
    depth: int = 0
    index: int = start
    in_quote: str | None = None
    while index < len(sql):
        character: str = sql[index]
        if in_quote is not None:
            if character == "\\":
                index += 2
                continue
            if character == in_quote:
                in_quote = None
            index += 1
            continue
        if character in _QUOTE_NAMES:
            in_quote = character
            index += 1
            continue
        if character == "(":
            depth += 1
            index += 1
            continue
        if character == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth == 0 and _keyword_at(sql, keyword, index):
            return index
        index += 1
    return None


def _split_top_level_select_items(sql: str, *, start: int, end: int) -> tuple[tuple[int, int], ...]:
    items: list[tuple[int, int]] = []
    depth: int = 0
    item_start: int = start
    index: int = start
    in_quote: str | None = None
    while index < end:
        character: str = sql[index]
        if in_quote is not None:
            if character == "\\":
                index += 2
                continue
            if character == in_quote:
                in_quote = None
            index += 1
            continue
        if character in _QUOTE_NAMES:
            in_quote = character
            index += 1
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            items.append((item_start, index))
            item_start = index + 1
        index += 1
    items.append((item_start, end))
    return tuple(items)


def _select_item_output_name(item: str) -> str | None:
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
        return None
    return bare_match.group("name").strip('"')


def _skip_local_whitespace(sql: str, start: int, end: int) -> int:
    while start < end and sql[start].isspace():
        start += 1
    return start


def _trim_local_whitespace(sql: str, start: int, end: int) -> int:
    while end > start and sql[end - 1].isspace():
        end -= 1
    return end


def _keyword_at(sql: str, keyword: str, index: int) -> bool:
    end: int = index + len(keyword)
    if sql[index:end].upper() != keyword:
        return False
    before: str = sql[index - 1] if index > 0 else " "
    after: str = sql[end] if end < len(sql) else " "
    return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")


def _parse_model_header(*, header: str, file_path: Path) -> dict[str, object]:
    try:
        parser: _ModelHeaderParser = _ModelHeaderParser(header=header)
        return parser.parse()
    except ModelSqlParseError:
        raise
    except ValueError as error:
        raise ModelSqlParseError(
            f"MODEL(...) in '{file_path}' contains invalid SQLBuild header syntax: {error}"
        ) from error


class _ModelHeaderParser:
    def __init__(self, *, header: str) -> None:
        self._tokens: list[_ModelHeaderToken] = _tokenize_model_header(header)
        self._index: int = 0

    def parse(self) -> dict[str, object]:
        if self._peek().kind == _END_TOKEN:
            return {}
        values: dict[str, object] = self._parse_map(end_symbol=None)
        self._expect_end()
        return values

    def _parse_map(self, *, end_symbol: str | None) -> dict[str, object]:
        values: dict[str, object] = {}
        while not self._is_at_end_symbol(end_symbol):
            if self._match_symbol(","):
                continue
            key: str = self._consume_key()
            if self._match_symbol(":"):
                raise ValueError(
                    f"unexpected ':' after key '{key}'; use SQLBuild syntax '{key} value'"
                )
            if self._is_at_end_symbol(end_symbol) or self._peek().kind == _END_TOKEN:
                raise ValueError(
                    f"unexpected token '{key}' without a value; quote values with spaces"
                )
            values[key] = self._parse_value()
            self._match_symbol(",")
        if end_symbol is not None:
            self._consume_symbol(end_symbol)
        return values

    def _parse_value(self) -> object:
        token: _ModelHeaderToken = self._peek()
        if token.kind == _STRING_TOKEN:
            self._advance()
            return token.value
        if token.kind == _WORD_TOKEN:
            self._advance()
            if self._peek().kind == _SYMBOL_TOKEN and self._peek().value == "(":
                self._advance()
                if token.value in _RELATION_CALL_NAMES:
                    return self._parse_relation_call(token.value)
                return {token.value: self._parse_map(end_symbol=")")}
            return _parse_word_value(token.value)
        if self._match_symbol("["):
            return self._parse_list()
        if self._match_symbol("("):
            return self._parse_map(end_symbol=")")
        raise ValueError(f"expected value at position {token.position}")

    def _parse_list(self) -> list[object]:
        values: list[object] = []
        while not self._is_at_end_symbol("]"):
            if self._match_symbol(","):
                continue
            values.append(self._parse_value())
            self._match_symbol(",")
        self._consume_symbol("]")
        return values

    def _parse_relation_call(self, name: str) -> str:
        token: _ModelHeaderToken = self._peek()
        if token.kind != _STRING_TOKEN:
            raise ValueError(f"{name}(...) requires a double-quoted relation name")
        self._advance()
        relation_name: str = token.value.replace('"', '\\"')
        self._consume_symbol(")")
        return f'{name}("{relation_name}")'

    def _consume_key(self) -> str:
        token: _ModelHeaderToken = self._peek()
        if token.kind != _WORD_TOKEN:
            raise ValueError(f"expected key at position {token.position}")
        self._advance()
        return token.value

    def _is_at_end_symbol(self, symbol: str | None) -> bool:
        token: _ModelHeaderToken = self._peek()
        if symbol is None:
            return token.kind == _END_TOKEN
        return token.kind == _SYMBOL_TOKEN and token.value == symbol

    def _match_symbol(self, symbol: str) -> bool:
        token: _ModelHeaderToken = self._peek()
        if token.kind == _SYMBOL_TOKEN and token.value == symbol:
            self._advance()
            return True
        return False

    def _consume_symbol(self, symbol: str) -> None:
        if self._match_symbol(symbol):
            return
        token: _ModelHeaderToken = self._peek()
        raise ValueError(f"expected '{symbol}' at position {token.position}")

    def _expect_end(self) -> None:
        token: _ModelHeaderToken = self._peek()
        if token.kind != _END_TOKEN:
            raise ValueError(f"unexpected token '{token.value}' at position {token.position}")

    def _peek(self) -> _ModelHeaderToken:
        return self._tokens[self._index]

    def _advance(self) -> _ModelHeaderToken:
        token: _ModelHeaderToken = self._tokens[self._index]
        self._index += 1
        return token


def _tokenize_model_header(header: str) -> list[_ModelHeaderToken]:
    tokens: list[_ModelHeaderToken] = []
    index: int = 0
    while index < len(header):
        character: str = header[index]
        if character.isspace():
            index += 1
            continue
        if character in _SYMBOLS:
            tokens.append(_ModelHeaderToken(kind=_SYMBOL_TOKEN, value=character, position=index))
            index += 1
            continue
        if character == ":":
            tokens.append(_ModelHeaderToken(kind=_SYMBOL_TOKEN, value=character, position=index))
            index += 1
            continue
        if character in _QUOTE_NAMES:
            string_value: str
            next_index: int
            string_value, next_index = _read_quoted_string(header=header, start=index)
            tokens.append(_ModelHeaderToken(kind=_STRING_TOKEN, value=string_value, position=index))
            index = next_index
            continue
        value: str
        next_index = index
        while next_index < len(header):
            next_character: str = header[next_index]
            if next_character.isspace() or next_character in _SYMBOLS or next_character == ":":
                break
            if next_character in _QUOTE_NAMES:
                raise ValueError(
                    f"unexpected {_QUOTE_NAMES[next_character]} quote inside bare value "
                    f"at position {next_index}; quote the whole value"
                )
            next_index += 1
        value = header[index:next_index]
        if not value:
            raise ValueError(f"unexpected character '{character}' at position {index}")
        tokens.append(_ModelHeaderToken(kind=_WORD_TOKEN, value=value, position=index))
        index = next_index
    tokens.append(_ModelHeaderToken(kind=_END_TOKEN, value="", position=len(header)))
    return tokens


def _read_quoted_string(*, header: str, start: int) -> tuple[str, int]:
    value_parts: list[str] = []
    quote: str = header[start]
    quote_name: str = _QUOTE_NAMES[quote]
    index: int = start + 1
    while index < len(header):
        character: str = header[index]
        if character == "\\":
            if index + 1 >= len(header):
                raise ValueError(f"unterminated escape at position {index}")
            value_parts.append(header[index + 1])
            index += 2
            continue
        if character == quote:
            return "".join(value_parts), index + 1
        value_parts.append(character)
        index += 1
    raise ValueError(f"unterminated {quote_name}-quoted string at position {start}")


def _parse_word_value(value: str) -> object:
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    if _INTEGER_PATTERN.match(value):
        return int(value)
    if _FLOAT_PATTERN.match(value):
        return float(value)
    return value
