"""Parsing helpers for authored SQL model files."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery.exceptions import ModelHeaderSyntaxError, ModelSqlParseError
from sqlbuild.compiler.discovery.models import PythonHookEntry, SqlHookEntry
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SourceLocation

_MODEL_HEADER_END_TOKEN: str = "end"
_MODEL_HEADER_WORD_TOKEN: str = "word"
_MODEL_HEADER_STRING_TOKEN: str = "string"
_MODEL_HEADER_SYMBOL_TOKEN: str = "symbol"
_MODEL_HEADER_SYMBOLS: frozenset[str] = frozenset({"(", ")", "[", "]", ","})
_MODEL_HEADER_OPEN_PAREN: str = "("
_MODEL_HEADER_CLOSE_PAREN: str = ")"
_MODEL_HEADER_OPEN_BRACKET: str = "["
_MODEL_HEADER_CLOSE_BRACKET: str = "]"
_MODEL_HEADER_COMMA: str = ","
_MODEL_HEADER_KEY_VALUE_SEPARATOR: str = ":"
_MODEL_HEADER_QUOTE_NAMES: dict[str, str] = {"'": "single", '"': "double"}
_MODEL_HEADER_ESCAPE_CHARACTER: str = "\\"
_MODEL_HEADER_COLUMNS_KEY: str = "columns"
_MODEL_HEADER_RELATION_CALL_NAMES: frozenset[str] = frozenset(
    {
        SqlReferenceKind.REF.function_name,
        SqlReferenceKind.SEED.function_name,
        SqlReferenceKind.SOURCE.function_name,
    }
)
_MODEL_HEADER_SQL_HOOK_CALL: str = "sql"
_MODEL_HEADER_HOOK_CALL_NAMES: frozenset[str] = frozenset({_MODEL_HEADER_SQL_HOOK_CALL, "python"})
_MODEL_HEADER_HOOK_FIELD_NAMES: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_MODEL_HEADER_TRUE_VALUE: str = "true"
_MODEL_HEADER_FALSE_VALUE: str = "false"
_MODEL_HEADER_NULL_VALUE: str = "null"
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
_MODEL_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*MODEL\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)


@dataclass(frozen=True)
class _ModelHeaderToken:
    kind: str
    value: str
    position: int


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
    header: str = header_match.group("header")
    header_start: int = header_match.start("header")
    tokens: list[_ModelHeaderToken] = _tokenize_model_header(header)
    line_starts: tuple[int, ...] | None = None
    locations: dict[str, SourceLocation] = {}
    depth: int = 0
    in_columns: bool = False
    token_index: int = 0
    while token_index < len(tokens):
        token: _ModelHeaderToken = tokens[token_index]
        if token.kind == _MODEL_HEADER_END_TOKEN:
            break
        if (
            token.kind == _MODEL_HEADER_WORD_TOKEN
            and token.value == _MODEL_HEADER_COLUMNS_KEY
            and depth == 0
        ):
            next_token: _ModelHeaderToken = tokens[token_index + 1]
            if (
                next_token.kind == _MODEL_HEADER_SYMBOL_TOKEN
                and next_token.value == _MODEL_HEADER_OPEN_PAREN
            ):
                in_columns = True
        elif in_columns and token.kind == _MODEL_HEADER_WORD_TOKEN and depth == 1:
            if line_starts is None:
                line_starts = _line_starts(contents)
            locations[token.value] = _location_for_header_token(
                contents=contents,
                header_start=header_start,
                token=token,
                relative_path=relative_path,
                line_starts=line_starts,
            )
        if token.kind == _MODEL_HEADER_SYMBOL_TOKEN and token.value == _MODEL_HEADER_OPEN_PAREN:
            depth += 1
        elif token.kind == _MODEL_HEADER_SYMBOL_TOKEN and token.value == _MODEL_HEADER_CLOSE_PAREN:
            depth -= 1
            if in_columns and depth == 0:
                break
        token_index += 1
    return locations


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


def _location_for_header_token(
    *,
    contents: str,
    header_start: int,
    token: _ModelHeaderToken,
    relative_path: Path,
    line_starts: tuple[int, ...],
) -> SourceLocation:
    absolute_position: int = header_start + token.position
    return _location_for_absolute_span(
        contents=contents,
        start=absolute_position,
        end=absolute_position + len(token.value),
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


def _find_top_level_keyword(*, sql: str, keyword: str, start: int) -> int | None:
    depth: int = 0
    index: int = start
    in_quote: str | None = None
    while index < len(sql):
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
        if depth == 0 and _keyword_at(sql=sql, keyword=keyword, index=index):
            return index
        index += 1
    return None


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


def parse_header_values(*, header: str, file_path: Path, statement_name: str) -> dict[str, object]:
    """Parse one SQLBuild parenthesized header into nested Python values."""

    try:
        parser: _ModelHeaderParser = _ModelHeaderParser(header=header)
        return parser.parse()
    except ModelSqlParseError:
        raise
    except ModelHeaderSyntaxError as error:
        raise ModelSqlParseError(
            f"{statement_name}(...) in '{file_path}' contains invalid SQLBuild header syntax: "
            f"{error}"
        ) from error


class _ModelHeaderParser:
    def __init__(self, *, header: str) -> None:
        self._tokens: list[_ModelHeaderToken] = _tokenize_model_header(header)
        self._index: int = 0

    def parse(self) -> dict[str, object]:
        if self._peek().kind == _MODEL_HEADER_END_TOKEN:
            return {}
        values: dict[str, object] = self._parse_map(end_symbol=None)
        self._expect_end()
        return values

    def _parse_map(self, *, end_symbol: str | None) -> dict[str, object]:
        values: dict[str, object] = {}
        while not self._is_at_end_symbol(end_symbol):
            if self._match_symbol(_MODEL_HEADER_COMMA):
                continue
            key: str = self._consume_key()
            if key in values:
                raise ModelHeaderSyntaxError(f"duplicate key '{key}'")
            if self._match_symbol(_MODEL_HEADER_KEY_VALUE_SEPARATOR):
                raise ModelHeaderSyntaxError(
                    f"unexpected ':' after key '{key}'; use SQLBuild syntax '{key} value'"
                )
            if self._is_at_end_symbol(end_symbol) or self._peek().kind == _MODEL_HEADER_END_TOKEN:
                raise ModelHeaderSyntaxError(
                    f"unexpected token '{key}' without a value; quote values with spaces"
                )
            values[key] = (
                self._parse_hook_field_value(key)
                if key in _MODEL_HEADER_HOOK_FIELD_NAMES
                else self._parse_value()
            )
            self._match_symbol(_MODEL_HEADER_COMMA)
        if end_symbol is not None:
            self._consume_symbol(end_symbol)
        return values

    def _parse_value(self) -> object:
        token: _ModelHeaderToken = self._peek()
        if token.kind == _MODEL_HEADER_STRING_TOKEN:
            self._advance()
            return token.value
        if token.kind == _MODEL_HEADER_WORD_TOKEN:
            self._advance()
            if (
                self._peek().kind == _MODEL_HEADER_SYMBOL_TOKEN
                and self._peek().value == _MODEL_HEADER_OPEN_PAREN
            ):
                self._advance()
                if token.value in _MODEL_HEADER_RELATION_CALL_NAMES:
                    return self._parse_relation_call(token.value)
                if token.value in _MODEL_HEADER_HOOK_CALL_NAMES:
                    return self._parse_hook_call(token.value)
                return {token.value: self._parse_map(end_symbol=_MODEL_HEADER_CLOSE_PAREN)}
            return _parse_word_value(token.value)
        if self._match_symbol(_MODEL_HEADER_OPEN_BRACKET):
            return self._parse_list()
        if self._match_symbol(_MODEL_HEADER_OPEN_PAREN):
            return self._parse_map(end_symbol=_MODEL_HEADER_CLOSE_PAREN)
        raise ModelHeaderSyntaxError(f"expected value at position {token.position}")

    def _parse_list(self) -> list[object]:
        values: list[object] = []
        while not self._is_at_end_symbol(_MODEL_HEADER_CLOSE_BRACKET):
            if self._match_symbol(_MODEL_HEADER_COMMA):
                continue
            values.append(self._parse_value())
            self._match_symbol(_MODEL_HEADER_COMMA)
        self._consume_symbol(_MODEL_HEADER_CLOSE_BRACKET)
        return values

    def _parse_hook_field_value(self, field_name: str) -> list[object]:
        if not self._match_symbol(_MODEL_HEADER_OPEN_BRACKET):
            token: _ModelHeaderToken = self._peek()
            raise ModelHeaderSyntaxError(
                f"{field_name} must be a list of typed sql(...) or python(...) hook entries "
                f"at position {token.position}"
            )
        values: list[object] = []
        while not self._is_at_end_symbol(_MODEL_HEADER_CLOSE_BRACKET):
            if self._match_symbol(_MODEL_HEADER_COMMA):
                continue
            values.append(self._parse_hook_list_entry(field_name))
            self._match_symbol(_MODEL_HEADER_COMMA)
        self._consume_symbol(_MODEL_HEADER_CLOSE_BRACKET)
        return values

    def _parse_hook_list_entry(self, field_name: str) -> object:
        token: _ModelHeaderToken = self._peek()
        if token.kind == _MODEL_HEADER_STRING_TOKEN:
            self._advance()
            return token.value
        if token.kind != _MODEL_HEADER_WORD_TOKEN:
            raise ModelHeaderSyntaxError(
                f"{field_name} entries must use typed sql(...) or python(...) hook syntax"
            )
        self._advance()
        if (
            self._peek().kind != _MODEL_HEADER_SYMBOL_TOKEN
            or self._peek().value != _MODEL_HEADER_OPEN_PAREN
        ):
            raise ModelHeaderSyntaxError(
                f"{field_name} entries must use typed sql(...) or python(...) hook syntax"
            )
        self._advance()
        if token.value not in _MODEL_HEADER_HOOK_CALL_NAMES:
            raise ModelHeaderSyntaxError(
                f"{field_name} entries must use typed sql(...) or python(...) hook syntax"
            )
        return self._parse_hook_call(token.value)

    def _parse_relation_call(self, name: str) -> str:
        token: _ModelHeaderToken = self._peek()
        if token.kind != _MODEL_HEADER_STRING_TOKEN:
            raise ModelHeaderSyntaxError(f"{name}(...) requires a double-quoted relation name")
        self._advance()
        relation_name: str = token.value.replace('"', '\\"')
        self._consume_symbol(_MODEL_HEADER_CLOSE_PAREN)
        return f'{name}("{relation_name}")'

    def _parse_hook_call(self, name: str) -> SqlHookEntry | PythonHookEntry:
        if name == _MODEL_HEADER_SQL_HOOK_CALL:
            statement_token: _ModelHeaderToken = self._peek()
            if statement_token.kind != _MODEL_HEADER_STRING_TOKEN:
                raise ModelHeaderSyntaxError("sql(...) requires a quoted SQL string")
            self._advance()
            if self._match_symbol(_MODEL_HEADER_COMMA):
                raise ModelHeaderSyntaxError("sql(...) does not accept additional arguments")
            self._consume_symbol(_MODEL_HEADER_CLOSE_PAREN)
            return SqlHookEntry(statement=statement_token.value)

        hook_name_token: _ModelHeaderToken = self._peek()
        if hook_name_token.kind != _MODEL_HEADER_STRING_TOKEN:
            raise ModelHeaderSyntaxError("python(...) requires a quoted hook name")
        self._advance()
        kwargs: dict[str, object] = {}
        while self._match_symbol(_MODEL_HEADER_COMMA):
            if self._is_at_end_symbol(_MODEL_HEADER_CLOSE_PAREN):
                break
            key: str = self._consume_key()
            self._consume_symbol(_MODEL_HEADER_KEY_VALUE_SEPARATOR)
            kwargs[key] = self._parse_value()
        self._consume_symbol(_MODEL_HEADER_CLOSE_PAREN)
        return PythonHookEntry(name=hook_name_token.value, kwargs=kwargs)

    def _consume_key(self) -> str:
        token: _ModelHeaderToken = self._peek()
        if token.kind != _MODEL_HEADER_WORD_TOKEN:
            raise ModelHeaderSyntaxError(f"expected key at position {token.position}")
        self._advance()
        return token.value

    def _is_at_end_symbol(self, symbol: str | None) -> bool:
        token: _ModelHeaderToken = self._peek()
        if symbol is None:
            return token.kind == _MODEL_HEADER_END_TOKEN
        return token.kind == _MODEL_HEADER_SYMBOL_TOKEN and token.value == symbol

    def _match_symbol(self, symbol: str) -> bool:
        token: _ModelHeaderToken = self._peek()
        if token.kind == _MODEL_HEADER_SYMBOL_TOKEN and token.value == symbol:
            self._advance()
            return True
        return False

    def _consume_symbol(self, symbol: str) -> None:
        if self._match_symbol(symbol):
            return
        token: _ModelHeaderToken = self._peek()
        raise ModelHeaderSyntaxError(f"expected '{symbol}' at position {token.position}")

    def _expect_end(self) -> None:
        token: _ModelHeaderToken = self._peek()
        if token.kind != _MODEL_HEADER_END_TOKEN:
            raise ModelHeaderSyntaxError(
                f"unexpected token '{token.value}' at position {token.position}"
            )

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
        if character in _MODEL_HEADER_SYMBOLS:
            tokens.append(
                _ModelHeaderToken(kind=_MODEL_HEADER_SYMBOL_TOKEN, value=character, position=index)
            )
            index += 1
            continue
        if character == _MODEL_HEADER_KEY_VALUE_SEPARATOR:
            tokens.append(
                _ModelHeaderToken(kind=_MODEL_HEADER_SYMBOL_TOKEN, value=character, position=index)
            )
            index += 1
            continue
        if character in _MODEL_HEADER_QUOTE_NAMES:
            string_value: str
            next_index: int
            string_value, next_index = _read_quoted_string(header=header, start=index)
            tokens.append(
                _ModelHeaderToken(
                    kind=_MODEL_HEADER_STRING_TOKEN, value=string_value, position=index
                )
            )
            index = next_index
            continue
        value: str
        next_index = index
        while next_index < len(header):
            next_character: str = header[next_index]
            if (
                next_character.isspace()
                or next_character in _MODEL_HEADER_SYMBOLS
                or next_character == _MODEL_HEADER_KEY_VALUE_SEPARATOR
            ):
                break
            if next_character in _MODEL_HEADER_QUOTE_NAMES:
                raise ModelHeaderSyntaxError(
                    f"unexpected {_MODEL_HEADER_QUOTE_NAMES[next_character]} quote inside "
                    "bare value "
                    f"at position {next_index}; quote the whole value"
                )
            next_index += 1
        value = header[index:next_index]
        if not value:
            raise ModelHeaderSyntaxError(f"unexpected character '{character}' at position {index}")
        tokens.append(_ModelHeaderToken(kind=_MODEL_HEADER_WORD_TOKEN, value=value, position=index))
        index = next_index
    tokens.append(_ModelHeaderToken(kind=_MODEL_HEADER_END_TOKEN, value="", position=len(header)))
    return tokens


def _read_quoted_string(*, header: str, start: int) -> tuple[str, int]:
    value_parts: list[str] = []
    quote: str = header[start]
    quote_name: str = _MODEL_HEADER_QUOTE_NAMES[quote]
    index: int = start + 1
    while index < len(header):
        character: str = header[index]
        if character == _MODEL_HEADER_ESCAPE_CHARACTER:
            if index + 1 >= len(header):
                raise ModelHeaderSyntaxError(f"unterminated escape at position {index}")
            value_parts.append(header[index + 1])
            index += 2
            continue
        if character == quote:
            return "".join(value_parts), index + 1
        value_parts.append(character)
        index += 1
    raise ModelHeaderSyntaxError(f"unterminated {quote_name}-quoted string at position {start}")


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
