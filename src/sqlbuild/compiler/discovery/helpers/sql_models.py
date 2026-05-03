"""Parsing helpers for authored SQL model files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery.exceptions import ModelSqlParseError
from sqlbuild.compiler.discovery.helpers.constants import MODEL_HEADER_PATTERN


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
_INTEGER_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?\d+$")
_FLOAT_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)$")


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
        if character == "'":
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
            if next_character == "'":
                raise ValueError(f"unexpected quote inside bare value at position {next_index}")
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
    index: int = start + 1
    while index < len(header):
        character: str = header[index]
        if character == "\\":
            if index + 1 >= len(header):
                raise ValueError(f"unterminated escape at position {index}")
            value_parts.append(header[index + 1])
            index += 2
            continue
        if character == "'":
            return "".join(value_parts), index + 1
        value_parts.append(character)
        index += 1
    raise ValueError(f"unterminated quoted string at position {start}")


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
