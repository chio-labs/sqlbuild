"""Extract normalised `fn` item units from Rust sources."""

from __future__ import annotations

from pathlib import PurePosixPath

from scripts.dupscore._helpers.clones.rust_lexer import lex_rust
from scripts.dupscore._helpers.clones.tokens import build_clone_unit
from scripts.dupscore.constants import (
    LANGUAGE_RUST,
    PLACEHOLDER_BYTE,
    PLACEHOLDER_BYTE_STRING,
    PLACEHOLDER_CHAR,
    PLACEHOLDER_IDENTIFIER,
    PLACEHOLDER_LIFETIME,
    PLACEHOLDER_NUMBER,
    PLACEHOLDER_STRING,
    RUST_KIND_BYTE,
    RUST_KIND_BYTE_STRING,
    RUST_KIND_CHAR,
    RUST_KIND_IDENTIFIER,
    RUST_KIND_LIFETIME,
    RUST_KIND_NUMBER,
    RUST_KIND_PUNCTUATION,
    RUST_KIND_STRING,
)
from scripts.dupscore.models import CloneUnit, RustFileUnits, RustToken

_RUST_KEYWORDS: frozenset[str] = frozenset(
    {
        "as",
        "async",
        "await",
        "break",
        "const",
        "continue",
        "crate",
        "dyn",
        "else",
        "enum",
        "extern",
        "false",
        "fn",
        "for",
        "if",
        "impl",
        "in",
        "let",
        "loop",
        "match",
        "mod",
        "move",
        "mut",
        "pub",
        "ref",
        "return",
        "self",
        "Self",
        "static",
        "struct",
        "super",
        "trait",
        "true",
        "type",
        "unsafe",
        "use",
        "where",
        "while",
    }
)
_LITERAL_PLACEHOLDERS: dict[str, str] = {
    RUST_KIND_STRING: PLACEHOLDER_STRING,
    RUST_KIND_BYTE_STRING: PLACEHOLDER_BYTE_STRING,
    RUST_KIND_CHAR: PLACEHOLDER_CHAR,
    RUST_KIND_BYTE: PLACEHOLDER_BYTE,
    RUST_KIND_NUMBER: PLACEHOLDER_NUMBER,
    RUST_KIND_LIFETIME: PLACEHOLDER_LIFETIME,
}
_OPEN_BRACE: str = "{"
_SEMICOLON: str = ";"
_ATTRIBUTE_MARKER: str = "#"
_INNER_ATTRIBUTE_MARKER: str = "!"
_ATTRIBUTE_OPEN: str = "["
_OPENERS: dict[str, str] = {"{": "}", "(": ")", "[": "]"}
_CLOSERS: frozenset[str] = frozenset(_OPENERS.values())
_SIGNATURE_GROUP_OPENERS: frozenset[str] = frozenset({"(", "["})
_BODY_OR_END: frozenset[str] = frozenset({_OPEN_BRACE, _SEMICOLON})
_ANGLE_DEPTH_CHANGES: dict[str, int] = {"<": 1, ">": -1}
_FUNCTION_KEYWORD: str = "fn"
_OWNER_KEYWORDS: frozenset[str] = frozenset({"impl", "trait"})
_MACRO_RULES: str = "macro_rules"
_MODULE_KEYWORD: str = "mod"
_FOR_KEYWORD: str = "for"
_WHERE_KEYWORD: str = "where"
_MODULE_ROOT_FILES: frozenset[str] = frozenset({"mod.rs", "lib.rs", "main.rs"})
_TEST_ATTRIBUTE: str = "test"
_CFG_ATTRIBUTE: str = "cfg"
_NEGATION: str = "not"
_PATH_SEPARATOR: str = "::"
_RUST_SUFFIX: str = ".rs"
_DIRECTORY_SUFFIX: str = "/"
_OWNER_SEPARATOR: str = "::"


def extract_rust_units(
    *,
    relative_path: str,
    source: str,
    include_tests: bool,
) -> RustFileUnits:
    """Return every `fn` item with a body, skipping test-only items unless requested."""

    tokens: list[RustToken] = lex_rust(source)
    scanner: _ItemScanner = _ItemScanner(
        tokens=tokens,
        relative_path=relative_path,
        include_tests=include_tests,
    )
    scanner.scan(start=0, end=len(tokens), owner=None)
    return RustFileUnits(
        units=tuple(scanner.units),
        test_module_prefixes=tuple(scanner.test_module_prefixes),
    )


def _normalize(item: RustToken) -> str:
    if item.kind == RUST_KIND_IDENTIFIER:
        return item.text if item.text in _RUST_KEYWORDS else PLACEHOLDER_IDENTIFIER
    return _LITERAL_PLACEHOLDERS.get(item.kind, item.text)


def _match_brackets(tokens: list[RustToken]) -> list[int]:
    matches: list[int] = [-1] * len(tokens)
    stack: list[int] = []
    for index, item in enumerate(tokens):
        if item.kind != RUST_KIND_PUNCTUATION:
            continue
        if item.text in _OPENERS:
            stack.append(index)
        elif item.text in _CLOSERS and stack and _OPENERS[tokens[stack[-1]].text] == item.text:
            opener: int = stack.pop()
            matches[opener] = index
            matches[index] = opener
    return matches


def _is_test_attribute(texts: list[str]) -> bool:
    if not texts:
        return False
    if texts[0] == _CFG_ATTRIBUTE:
        return _TEST_ATTRIBUTE in texts and _NEGATION not in texts
    return texts[-1] == _TEST_ATTRIBUTE and all(
        text == _PATH_SEPARATOR or text.isidentifier() for text in texts
    )


def _strip_leading_generics(header: list[RustToken]) -> list[RustToken]:
    depth: int = 0
    for position, item in enumerate(header):
        depth += _ANGLE_DEPTH_CHANGES.get(item.text, 0)
        if depth == 0:
            return header if position == 0 else header[position + 1 :]
    return []


def _owner_name(header: list[RustToken]) -> str | None:
    """Name the self type of an ``impl`` or ``trait`` header (tokens between it and ``{``)."""

    candidates: list[RustToken] = _strip_leading_generics(header)
    depth: int = 0
    for position, item in enumerate(candidates):
        depth += _ANGLE_DEPTH_CHANGES.get(item.text, 0)
        if depth == 0 and item.text == _FOR_KEYWORD:
            candidates = candidates[position + 1 :]
            break
    name: str | None = None
    depth = 0
    for item in candidates:
        depth += _ANGLE_DEPTH_CHANGES.get(item.text, 0)
        if depth == 0 and item.text == _WHERE_KEYWORD:
            break
        if depth == 0 and item.kind == RUST_KIND_IDENTIFIER and item.text not in _RUST_KEYWORDS:
            name = item.text
    return name


class _ItemScanner:
    def __init__(
        self,
        *,
        tokens: list[RustToken],
        relative_path: str,
        include_tests: bool,
    ) -> None:
        self._tokens: list[RustToken] = tokens
        self._matches: list[int] = _match_brackets(tokens)
        self._relative_path: str = relative_path
        self._include_tests: bool = include_tests
        self.units: list[CloneUnit] = []
        self.test_module_prefixes: list[str] = []

    def scan(self, *, start: int, end: int, owner: str | None) -> None:
        index: int = start
        test_item: bool = False
        item_start: int | None = None
        while index < end:
            attribute_end: int | None = self._attribute_end(index)
            if attribute_end is not None:
                test_item = test_item or self._attribute_is_test(index=index, end=attribute_end)
                index = attribute_end + 1
                continue
            if self._is_punctuation(index=index, text=_SEMICOLON):
                index += 1
                test_item, item_start = False, None
                continue
            if test_item and not self._include_tests:
                self._record_test_module(index)
                index = self._item_end(start=index, end=end)
                test_item, item_start = False, None
                continue
            if item_start is None:
                item_start = index
            next_index: int | None = self._scan_item(
                index=index, end=end, owner=owner, item_start=item_start
            )
            if next_index is None:
                index += 1
                continue
            index = next_index
            test_item, item_start = False, None

    def _scan_item(self, *, index: int, end: int, owner: str | None, item_start: int) -> int | None:
        item: RustToken = self._tokens[index]
        is_identifier: bool = item.kind == RUST_KIND_IDENTIFIER
        if is_identifier and item.text == _FUNCTION_KEYWORD and self._is_identifier(index + 1):
            body: int = self._find_body(start=index + 2, end=end)
            if not self._is_punctuation(index=body, text=_OPEN_BRACE) or body >= end:
                return body + 1
            close: int = self._closing(opener=body, end=end)
            self._emit_unit(start=index, close=close, owner=owner, item_start=item_start)
            return close + 1
        if is_identifier and item.text in _OWNER_KEYWORDS:
            body = self._find_body(start=index + 1, end=end)
            if not self._is_punctuation(index=body, text=_OPEN_BRACE) or body >= end:
                return body + 1
            close = self._closing(opener=body, end=end)
            self.scan(
                start=body + 1,
                end=close,
                owner=_owner_name(self._tokens[index + 1 : body]),
            )
            return close + 1
        if is_identifier and item.text == _MACRO_RULES:
            body = index + 1
            while body < end and self._tokens[body].text not in _OPENERS:
                body += 1
            return self._closing(opener=body, end=end) + 1 if body < end else end
        if self._is_punctuation(index=index, text=_OPEN_BRACE):
            close = self._closing(opener=index, end=end)
            self.scan(start=index + 1, end=close, owner=owner)
            return close + 1
        return None

    def _is_punctuation(self, *, index: int, text: str) -> bool:
        return (
            index < len(self._tokens)
            and self._tokens[index].kind == RUST_KIND_PUNCTUATION
            and self._tokens[index].text == text
        )

    def _is_identifier(self, index: int) -> bool:
        return index < len(self._tokens) and self._tokens[index].kind == RUST_KIND_IDENTIFIER

    def _attribute_open(self, index: int) -> int | None:
        if not self._is_punctuation(index=index, text=_ATTRIBUTE_MARKER):
            return None
        opener: int = index + 1
        if self._is_punctuation(index=opener, text=_INNER_ATTRIBUTE_MARKER):
            opener += 1
        return opener if self._is_punctuation(index=opener, text=_ATTRIBUTE_OPEN) else None

    def _attribute_end(self, index: int) -> int | None:
        opener: int | None = self._attribute_open(index)
        if opener is None:
            return None
        close: int = self._matches[opener]
        return close if close > opener else None

    def _attribute_is_test(self, *, index: int, end: int) -> bool:
        opener: int | None = self._attribute_open(index)
        if opener is None:
            return False
        return _is_test_attribute([item.text for item in self._tokens[opener + 1 : end]])

    def _closing(self, *, opener: int, end: int) -> int:
        close: int = self._matches[opener]
        return close if opener < close < end else end - 1

    def _find_body(self, *, start: int, end: int) -> int:
        index: int = start
        while index < end:
            item: RustToken = self._tokens[index]
            if item.kind == RUST_KIND_PUNCTUATION and item.text in _BODY_OR_END:
                return index
            if item.kind == RUST_KIND_PUNCTUATION and item.text in _SIGNATURE_GROUP_OPENERS:
                index = self._closing(opener=index, end=end) + 1
                continue
            index += 1
        return end

    def _item_end(self, *, start: int, end: int) -> int:
        body: int = self._find_body(start=start, end=end)
        if body >= end:
            return end
        if self._is_punctuation(index=body, text=_OPEN_BRACE):
            return self._closing(opener=body, end=end) + 1
        return body + 1

    def _record_test_module(self, index: int) -> None:
        if not (
            self._tokens[index].text == _MODULE_KEYWORD
            and self._is_identifier(index + 1)
            and self._is_punctuation(index=index + 2, text=_SEMICOLON)
        ):
            return
        path: PurePosixPath = PurePosixPath(self._relative_path)
        base: PurePosixPath = (
            path.parent if path.name in _MODULE_ROOT_FILES else path.parent / path.stem
        )
        module_path: str = (base / self._tokens[index + 1].text).as_posix()
        self.test_module_prefixes.append(module_path + _RUST_SUFFIX)
        self.test_module_prefixes.append(module_path + _DIRECTORY_SUFFIX)

    def _emit_unit(self, *, start: int, close: int, owner: str | None, item_start: int) -> None:
        function_name: str = self._tokens[start + 1].text
        body: list[RustToken] = self._tokens[start : close + 1]
        self.units.append(
            build_clone_unit(
                language=LANGUAGE_RUST,
                path=self._relative_path,
                name=f"{owner}{_OWNER_SEPARATOR}{function_name}" if owner else function_name,
                start_line=self._tokens[item_start].line,
                end_line=self._tokens[close].line,
                normalized=[_normalize(item) for item in body],
                concrete=[item.text for item in body],
            )
        )
