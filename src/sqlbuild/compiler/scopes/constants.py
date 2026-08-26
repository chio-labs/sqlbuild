"""Constants for the compiler-owned scope domain."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind

SCOPE_METADATA_SCHEMA_VERSION: int = 1
SCOPE_CACHE_SCHEMA_VERSION: int = 1
SCOPE_FINGERPRINT_ALGORITHM_VERSION: int = 1
SCOPE_CACHE_DIRECTORY: Path = Path("target/compile-cache/declaration-scopes-v1")
SCOPE_CACHE_FILENAME: str = "scope-index.json"
SCOPE_CACHE_MAX_BYTES: int = 16 * 1024 * 1024
SCOPE_SOURCE_SUFFIXES: frozenset[str] = frozenset({".sql", ".yml", ".yaml", ".py"})
SCOPE_MACRO_SUFFIX: str = ".py"
SCOPE_RELATIONSHIP_ROOTS: frozenset[tuple[str, str]] = frozenset(
    {("tests", "unit"), ("tests", "scenarios")}
)
SCOPE_LOCAL_CONFIG_KEYS: frozenset[str] = frozenset(
    {"adapter", "settings", "target", "targets", "vars"}
)
SCOPE_PROJECT_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "adapter",
        "constants",
        "default_target",
        "defaults",
        "path_defaults",
        "settings",
        "targets",
        "vars",
    }
)
SCOPE_TARGET_VARS_KEY: str = "vars"
SCOPE_TARGETS_KEY: str = "targets"
SCOPE_ENUM_MEMBER_FIELDS: frozenset[str] = frozenset({"name"})
DEFAULT_ENUM_MEMBER_PREVIEW: int = 20
QUALIFIED_IDENTITY_SEPARATOR: str = ":"
PRIVATE_IDENTITY_SEPARATOR: str = "."
PATH_SEPARATOR: str = "/"
WINDOWS_PATH_SEPARATOR: str = "\\"
CURRENT_PATH_COMPONENT: str = "."
PARENT_PATH_COMPONENT: str = ".."
WINDOWS_DRIVE_SEPARATOR: str = ":"
WINDOWS_DRIVE_PREFIX_LENGTH: int = 2
PUBLIC_IDENTITY_PART_COUNT: int = 2
PRIVATE_IDENTITY_PART_COUNT: int = 3
EMPTY_TEXT: str = ""
AVAILABLE_SECTION: str = "available"
USED_SECTION: str = "used"
RELATIONSHIP_SECTION: str = "relationship_scope"
GLOBAL_SUMMARY_POLICY: str = "summary"
GLOBAL_USED_POLICY: str = "used"
GLOBAL_ALL_POLICY: str = "all"
LIST_SECTION: str = "list"
METADATA_FIELD: str = "metadata"
KIND_COUNTS_FIELD: str = "kind_counts"
DECLARATION_KIND_VALUES: frozenset[str] = frozenset(item.value for item in DeclarationKind)

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
