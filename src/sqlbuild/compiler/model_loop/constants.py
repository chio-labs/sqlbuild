"""Codes the native model loop shares with its Rust bindings."""

from sqlbuild.compiler.scopes.types import DeclarationKind

DECLARATION_KIND_CODES: dict[DeclarationKind, int] = {
    DeclarationKind.ENUM: 0,
    DeclarationKind.CONSTANT: 1,
    DeclarationKind.MACRO: 2,
}
NO_DECLARATION_KIND: int = 255
ENUM_REFERENCE_KIND_CODE: int = DECLARATION_KIND_CODES[DeclarationKind.ENUM]
UNCLOSED_QUOTE_STOP_CODE: int = 0
UNCLOSED_BLOCK_COMMENT_STOP_CODE: int = 1
INVALID_ENUM_REFERENCE_STOP_CODE: int = 2
INVALID_CONSTANT_REFERENCE_STOP_CODE: int = 3
