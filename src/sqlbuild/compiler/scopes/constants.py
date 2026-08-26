"""Constants for the compiler-owned scope domain."""

from __future__ import annotations

from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind

SCOPE_METADATA_SCHEMA_VERSION: int = 1
QUALIFIED_IDENTITY_SEPARATOR: str = ":"
PRIVATE_IDENTITY_SEPARATOR: str = "."
PATH_SEPARATOR: str = "/"
CURRENT_PATH_COMPONENT: str = "."
PARENT_PATH_COMPONENT: str = ".."
WINDOWS_DRIVE_SEPARATOR: str = ":"
WINDOWS_DRIVE_PREFIX_LENGTH: int = 2
PUBLIC_IDENTITY_PART_COUNT: int = 2
PRIVATE_IDENTITY_PART_COUNT: int = 3

GLOBAL_DECLARATION_DIRECTORIES: frozenset[str] = frozenset({"macros", "enums", "constants"})
INHERITED_DECLARATION_DIRECTORIES: frozenset[str] = frozenset({"_macros", "_enums", "_constants"})
LOCAL_DECLARATION_DIRECTORIES: frozenset[str] = frozenset(
    {"_local_macros", "_local_enums", "_local_constants"}
)
DECLARATION_DIRECTORY_FACTS: dict[str, tuple[DeclarationKind, ScopeKind]] = {
    "macros": (DeclarationKind.MACRO, ScopeKind.GLOBAL),
    "enums": (DeclarationKind.ENUM, ScopeKind.GLOBAL),
    "constants": (DeclarationKind.CONSTANT, ScopeKind.GLOBAL),
    "_macros": (DeclarationKind.MACRO, ScopeKind.INHERITED),
    "_enums": (DeclarationKind.ENUM, ScopeKind.INHERITED),
    "_constants": (DeclarationKind.CONSTANT, ScopeKind.INHERITED),
    "_local_macros": (DeclarationKind.MACRO, ScopeKind.LOCAL),
    "_local_enums": (DeclarationKind.ENUM, ScopeKind.LOCAL),
    "_local_constants": (DeclarationKind.CONSTANT, ScopeKind.LOCAL),
}
