"""A small Rust lexer that is precise enough for brace matching and clone tokens."""

from __future__ import annotations

from scripts.dupscore.constants import (
    RUST_KIND_BYTE,
    RUST_KIND_BYTE_STRING,
    RUST_KIND_CHAR,
    RUST_KIND_IDENTIFIER,
    RUST_KIND_LIFETIME,
    RUST_KIND_NUMBER,
    RUST_KIND_PUNCTUATION,
    RUST_KIND_STRING,
)
from scripts.dupscore.models import RustToken

_THREE_CHAR_OPERATORS: frozenset[str] = frozenset({"..=", "...", "<<=", ">>="})
_TWO_CHAR_OPERATORS: frozenset[str] = frozenset(
    {
        "::",
        "->",
        "=>",
        "==",
        "!=",
        "<=",
        ">=",
        "&&",
        "||",
        "+=",
        "-=",
        "*=",
        "/=",
        "%=",
        "^=",
        "&=",
        "|=",
        "..",
    }
)
_STRING_PREFIX_KINDS: dict[str, str] = {
    "b": RUST_KIND_BYTE_STRING,
    "br": RUST_KIND_BYTE_STRING,
    "c": RUST_KIND_STRING,
    "cr": RUST_KIND_STRING,
    "r": RUST_KIND_STRING,
}
_RAW_MARKER: str = "r"
_BYTE_PREFIX: str = "b"
_QUOTE: str = '"'
_APOSTROPHE: str = "'"
_BACKSLASH: str = "\\"
_HASH: str = "#"
_NEWLINE: str = "\n"
_UNDERSCORE: str = "_"
_DECIMAL_POINT: str = "."
_EXPONENT_MARKERS: frozenset[str] = frozenset({"e", "E"})
_EXPONENT_SIGNS: frozenset[str] = frozenset({"+", "-"})
_HEX_PREFIXES: tuple[str, ...] = ("0x", "0X")
_LINE_COMMENT: str = "//"
_BLOCK_COMMENT_OPEN: str = "/*"
_BLOCK_COMMENT_CLOSE: str = "*/"
_ESCAPE_WIDTH: int = 2
_EXPONENT_WIDTH: int = 2
_CHAR_AND_CLOSING_WIDTH: int = 2
_OPERATOR_WIDTHS: tuple[tuple[int, frozenset[str]], ...] = (
    (3, _THREE_CHAR_OPERATORS),
    (2, _TWO_CHAR_OPERATORS),
)


def lex_rust(source: str) -> list[RustToken]:
    """Tokenise Rust source, dropping whitespace and all comments."""

    lexer: _Lexer = _Lexer(source=source)
    return lexer.run()


def _is_word_start(character: str) -> bool:
    return character == _UNDERSCORE or character.isalpha()


def _is_word_part(character: str) -> bool:
    return character == _UNDERSCORE or character.isalnum()


class _Lexer:
    def __init__(self, *, source: str) -> None:
        self._source: str = source
        self._index: int = 0
        self._line: int = 1
        self._tokens: list[RustToken] = []

    def run(self) -> list[RustToken]:
        length: int = len(self._source)
        while self._index < length:
            character: str = self._source[self._index]
            if character == _NEWLINE:
                self._line += 1
                self._index += 1
            elif character.isspace():
                self._index += 1
            elif self._source.startswith(_LINE_COMMENT, self._index):
                self._skip_line_comment()
            elif self._source.startswith(_BLOCK_COMMENT_OPEN, self._index):
                self._skip_block_comment()
            elif character == _QUOTE:
                self._lex_quoted(kind=RUST_KIND_STRING, prefix_length=0)
            elif character == _APOSTROPHE:
                self._lex_apostrophe(prefix_length=0)
            elif character.isdigit():
                self._lex_number()
            elif _is_word_start(character):
                self._lex_word()
            else:
                self._lex_punctuation()
        return self._tokens

    def _emit(self, *, kind: str, start: int, line: int) -> None:
        text: str = self._source[start : self._index]
        self._tokens.append(RustToken(kind=kind, text=text, line=line))

    def _advance_to(self, end: int) -> None:
        self._line += self._source.count(_NEWLINE, self._index, end)
        self._index = end

    def _word_end(self, start: int) -> int:
        cursor: int = start
        while cursor < len(self._source) and _is_word_part(self._source[cursor]):
            cursor += 1
        return cursor

    def _skip_line_comment(self) -> None:
        end: int = self._source.find(_NEWLINE, self._index)
        self._index = len(self._source) if end < 0 else end

    def _skip_block_comment(self) -> None:
        depth: int = 0
        cursor: int = self._index
        length: int = len(self._source)
        while cursor < length:
            if self._source.startswith(_BLOCK_COMMENT_OPEN, cursor):
                depth += 1
                cursor += len(_BLOCK_COMMENT_OPEN)
            elif self._source.startswith(_BLOCK_COMMENT_CLOSE, cursor):
                depth -= 1
                cursor += len(_BLOCK_COMMENT_CLOSE)
                if depth == 0:
                    break
            else:
                cursor += 1
        self._advance_to(cursor)

    def _lex_word(self) -> None:
        start: int = self._index
        line: int = self._line
        cursor: int = self._word_end(start)
        word: str = self._source[start:cursor]
        following: str = self._source[cursor : cursor + 1]
        prefix_kind: str | None = _STRING_PREFIX_KINDS.get(word)
        if prefix_kind is not None and following in (_QUOTE, _HASH):
            if word.endswith(_RAW_MARKER):
                if self._lex_raw_string(kind=prefix_kind, prefix_end=cursor):
                    return
            elif following == _QUOTE:
                self._lex_quoted(kind=prefix_kind, prefix_length=cursor - start)
                return
        if word == _BYTE_PREFIX and following == _APOSTROPHE:
            self._lex_apostrophe(prefix_length=len(_BYTE_PREFIX))
            return
        if word == _RAW_MARKER and following == _HASH and self._is_raw_identifier(cursor):
            cursor = self._word_end(cursor + 1)
        self._index = cursor
        self._emit(kind=RUST_KIND_IDENTIFIER, start=start, line=line)

    def _is_raw_identifier(self, hash_index: int) -> bool:
        after: int = hash_index + 1
        return after < len(self._source) and _is_word_start(self._source[after])

    def _lex_raw_string(self, *, kind: str, prefix_end: int) -> bool:
        start: int = self._index
        line: int = self._line
        cursor: int = prefix_end
        hashes: int = 0
        while cursor < len(self._source) and self._source[cursor] == _HASH:
            hashes += 1
            cursor += 1
        if cursor >= len(self._source) or self._source[cursor] != _QUOTE:
            return False
        terminator: str = _QUOTE + _HASH * hashes
        end: int = self._source.find(terminator, cursor + 1)
        end = len(self._source) if end < 0 else end + len(terminator)
        self._advance_to(end)
        self._emit(kind=kind, start=start, line=line)
        return True

    def _lex_quoted(self, *, kind: str, prefix_length: int) -> None:
        start: int = self._index
        line: int = self._line
        cursor: int = start + prefix_length + 1
        length: int = len(self._source)
        while cursor < length and self._source[cursor] != _QUOTE:
            cursor += _ESCAPE_WIDTH if self._source[cursor] == _BACKSLASH else 1
        self._advance_to(min(cursor + 1, length))
        self._emit(kind=kind, start=start, line=line)

    def _lex_apostrophe(self, *, prefix_length: int) -> None:
        start: int = self._index
        line: int = self._line
        after: int = start + prefix_length + 1
        length: int = len(self._source)
        kind: str = RUST_KIND_BYTE if prefix_length else RUST_KIND_CHAR
        if after < length and self._source[after] == _BACKSLASH:
            closing: int = self._source.find(_APOSTROPHE, after + _ESCAPE_WIDTH)
            self._index = length if closing < 0 else closing + 1
            self._emit(kind=kind, start=start, line=line)
            return
        if after + 1 < length and self._source[after + 1] == _APOSTROPHE:
            self._index = after + _CHAR_AND_CLOSING_WIDTH
            self._emit(kind=kind, start=start, line=line)
            return
        self._index = self._word_end(after)
        self._emit(kind=RUST_KIND_LIFETIME, start=start, line=line)

    def _lex_number(self) -> None:
        start: int = self._index
        line: int = self._line
        cursor: int = start
        length: int = len(self._source)
        hexadecimal: bool = self._source.startswith(_HEX_PREFIXES, start)
        while cursor < length:
            character: str = self._source[cursor]
            following: str = self._source[cursor + 1 : cursor + 2]
            if not hexadecimal and character in _EXPONENT_MARKERS and following in _EXPONENT_SIGNS:
                cursor += _EXPONENT_WIDTH
            elif _is_word_part(character) or (character == _DECIMAL_POINT and following.isdigit()):
                cursor += 1
            else:
                break
        self._index = cursor
        self._emit(kind=RUST_KIND_NUMBER, start=start, line=line)

    def _lex_punctuation(self) -> None:
        start: int = self._index
        line: int = self._line
        for width, operators in _OPERATOR_WIDTHS:
            if self._source[start : start + width] in operators:
                self._index = start + width
                self._emit(kind=RUST_KIND_PUNCTUATION, start=start, line=line)
                return
        self._index = start + 1
        self._emit(kind=RUST_KIND_PUNCTUATION, start=start, line=line)
