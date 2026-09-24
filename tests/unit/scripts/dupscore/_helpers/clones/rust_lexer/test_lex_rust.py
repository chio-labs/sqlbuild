from __future__ import annotations

import pytest

from scripts.dupscore._helpers.clones.rust_lexer import lex_rust
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
from tests.unit.scripts.dupscore._helpers.clones.rust_lexer._test_types import (
    LexLineTestCase,
    LexRustTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LexRustTestCase(
            description="raw string containing braces and quotes is one token",
            source='let s = r#"{ "a" } }"#;',
            expected_tokens=(
                (RUST_KIND_IDENTIFIER, "let"),
                (RUST_KIND_IDENTIFIER, "s"),
                (RUST_KIND_PUNCTUATION, "="),
                (RUST_KIND_STRING, 'r#"{ "a" } }"#'),
                (RUST_KIND_PUNCTUATION, ";"),
            ),
        ),
        LexRustTestCase(
            description="lifetimes are distinguished from char literals",
            source="fn f<'a>(x: &'a str) -> char { '{' }",
            expected_tokens=(
                (RUST_KIND_IDENTIFIER, "fn"),
                (RUST_KIND_IDENTIFIER, "f"),
                (RUST_KIND_PUNCTUATION, "<"),
                (RUST_KIND_LIFETIME, "'a"),
                (RUST_KIND_PUNCTUATION, ">"),
                (RUST_KIND_PUNCTUATION, "("),
                (RUST_KIND_IDENTIFIER, "x"),
                (RUST_KIND_PUNCTUATION, ":"),
                (RUST_KIND_PUNCTUATION, "&"),
                (RUST_KIND_LIFETIME, "'a"),
                (RUST_KIND_IDENTIFIER, "str"),
                (RUST_KIND_PUNCTUATION, ")"),
                (RUST_KIND_PUNCTUATION, "->"),
                (RUST_KIND_IDENTIFIER, "char"),
                (RUST_KIND_PUNCTUATION, "{"),
                (RUST_KIND_CHAR, "'{'"),
                (RUST_KIND_PUNCTUATION, "}"),
            ),
        ),
        LexRustTestCase(
            description="nested block comments and line comments are dropped",
            source="/* outer /* inner { */ still } */ x // trailing {\ny",
            expected_tokens=((RUST_KIND_IDENTIFIER, "x"), (RUST_KIND_IDENTIFIER, "y")),
        ),
        LexRustTestCase(
            description="escaped chars and byte literals are single tokens",
            source=r"""'\'' '\u{7B}' b'}' b"{\"}" br#"}"# 'static""",
            expected_tokens=(
                (RUST_KIND_CHAR, r"'\''"),
                (RUST_KIND_CHAR, r"'\u{7B}'"),
                (RUST_KIND_BYTE, "b'}'"),
                (RUST_KIND_BYTE_STRING, r'b"{\"}"'),
                (RUST_KIND_BYTE_STRING, 'br#"}"#'),
                (RUST_KIND_LIFETIME, "'static"),
            ),
        ),
        LexRustTestCase(
            description="numbers keep suffixes and ranges stay separate",
            source="0..10u8 1.5e-3 0xFF_u32 t.0",
            expected_tokens=(
                (RUST_KIND_NUMBER, "0"),
                (RUST_KIND_PUNCTUATION, ".."),
                (RUST_KIND_NUMBER, "10u8"),
                (RUST_KIND_NUMBER, "1.5e-3"),
                (RUST_KIND_NUMBER, "0xFF_u32"),
                (RUST_KIND_IDENTIFIER, "t"),
                (RUST_KIND_PUNCTUATION, "."),
                (RUST_KIND_NUMBER, "0"),
            ),
        ),
        LexRustTestCase(
            description="raw identifiers and path separators",
            source="r#type::new()",
            expected_tokens=(
                (RUST_KIND_IDENTIFIER, "r#type"),
                (RUST_KIND_PUNCTUATION, "::"),
                (RUST_KIND_IDENTIFIER, "new"),
                (RUST_KIND_PUNCTUATION, "("),
                (RUST_KIND_PUNCTUATION, ")"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rust_source_when_lexing_then_returns_expected_tokens(
    test_case: LexRustTestCase,
) -> None:
    tokens: list[RustToken] = lex_rust(test_case.source)

    assert tuple((item.kind, item.text) for item in tokens) == test_case.expected_tokens


@pytest.mark.parametrize(
    "test_case",
    [
        LexLineTestCase(
            description="multi-line string advances the line counter",
            source='let a = "one\ntwo\nthree";\nlet b = 1;',
            token_text="b",
            expected_line=4,
        ),
        LexLineTestCase(
            description="multi-line block comment advances the line counter",
            source="/* one\n/* two\n*/ three\n*/\nafter",
            token_text="after",
            expected_line=5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_multiline_tokens_when_lexing_then_tracks_lines(
    test_case: LexLineTestCase,
) -> None:
    tokens: list[RustToken] = lex_rust(test_case.source)

    lines_by_text: dict[str, int] = {item.text: item.line for item in tokens}
    assert lines_by_text[test_case.token_text] == test_case.expected_line
