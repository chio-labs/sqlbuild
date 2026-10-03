"""Constants for the compiler-owned scope domain."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind

SCOPE_METADATA_SCHEMA_VERSION: int = 3
SCOPE_CACHE_SCHEMA_VERSION: int = 3
SCOPE_FINGERPRINT_ALGORITHM_VERSION: int = 2
SCOPE_CACHE_DIRECTORY: Path = Path("target/cache/compiler/declaration-scopes-v2")
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
        "scopes",
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

DECLARATION_GROUP_DIRECTORY: str = "_sqlbuild"
GLOBAL_DECLARATION_DIRECTORIES: frozenset[str] = frozenset({"macros", "enums", "constants"})
INHERITED_DECLARATION_DIRECTORIES: frozenset[str] = GLOBAL_DECLARATION_DIRECTORIES
LOCAL_DECLARATION_DIRECTORIES: frozenset[str] = frozenset({"_macros", "_enums", "_constants"})
SCOPED_DECLARATION_DIRECTORIES: frozenset[str] = (
    INHERITED_DECLARATION_DIRECTORIES | LOCAL_DECLARATION_DIRECTORIES
)
DECLARATION_DIRECTORY_FACTS: dict[str, tuple[DeclarationKind, ScopeKind]] = {
    "macros": (DeclarationKind.MACRO, ScopeKind.INHERITED),
    "enums": (DeclarationKind.ENUM, ScopeKind.INHERITED),
    "constants": (DeclarationKind.CONSTANT, ScopeKind.INHERITED),
    "_macros": (DeclarationKind.MACRO, ScopeKind.LOCAL),
    "_enums": (DeclarationKind.ENUM, ScopeKind.LOCAL),
    "_constants": (DeclarationKind.CONSTANT, ScopeKind.LOCAL),
}

GLOBAL_NAMED_DECLARATION_ROOTS: dict[tuple[str, ...], DeclarationKind] = {
    ("audits", "generic"): DeclarationKind.AUDIT,
    ("audits", "singular"): DeclarationKind.SINGULAR_AUDIT,
    ("schemas",): DeclarationKind.SCHEMA,
    ("hooks", "sql"): DeclarationKind.SQL_HOOK,
    ("hooks", "python"): DeclarationKind.PYTHON_HOOK,
}
GROUPED_NAMED_DECLARATION_ROLES: dict[tuple[str, ...], tuple[DeclarationKind, ScopeKind]] = {
    ("audits", "generic"): (DeclarationKind.AUDIT, ScopeKind.INHERITED),
    ("_audits", "generic"): (DeclarationKind.AUDIT, ScopeKind.LOCAL),
    ("audits", "singular"): (DeclarationKind.SINGULAR_AUDIT, ScopeKind.INHERITED),
    ("schemas",): (DeclarationKind.SCHEMA, ScopeKind.INHERITED),
    ("_schemas",): (DeclarationKind.SCHEMA, ScopeKind.LOCAL),
    ("hooks", "sql"): (DeclarationKind.SQL_HOOK, ScopeKind.INHERITED),
    ("_hooks", "sql"): (DeclarationKind.SQL_HOOK, ScopeKind.LOCAL),
    ("hooks", "python"): (DeclarationKind.PYTHON_HOOK, ScopeKind.INHERITED),
    ("_hooks", "python"): (DeclarationKind.PYTHON_HOOK, ScopeKind.LOCAL),
}
GROUPED_NAMED_DECLARATION_DIRECTORIES: frozenset[str] = frozenset(
    role[0] for role in GROUPED_NAMED_DECLARATION_ROLES
)
GLOBAL_NAMED_DECLARATION_DIRECTORIES: frozenset[str] = frozenset(
    role[0] for role in GLOBAL_NAMED_DECLARATION_ROOTS
)
NAMED_DECLARATION_KINDS: frozenset[DeclarationKind] = frozenset(
    GLOBAL_NAMED_DECLARATION_ROOTS.values()
)
DECLARATION_ROLE_PARTS: dict[DeclarationKind, tuple[str, ...]] = {
    DeclarationKind.MACRO: ("macros",),
    DeclarationKind.ENUM: ("enums",),
    DeclarationKind.CONSTANT: ("constants",),
    **{kind: role for role, kind in GLOBAL_NAMED_DECLARATION_ROOTS.items()},
}
