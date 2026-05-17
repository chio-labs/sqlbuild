"""Stable constants for structure convention checks."""

BANNED_GENERIC_FILENAMES: frozenset[str] = frozenset(
    {"base.py", "common.py", "helpers.py", "misc.py"}
)
DEV_TOOLING_SEGMENTS: frozenset[str] = frozenset({"checks", "tooling"})
DEV_TOOLING_FILE_PREFIXES: tuple[str, ...] = ("check_", "format_", "lint_", "test_")
TYPE_CLASS_BASE_NAMES: frozenset[str] = frozenset(
    {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "NamedTuple", "Protocol", "TypedDict"}
)
MODEL_CLASS_BASE_NAMES: frozenset[str] = frozenset({"BaseModel"})
RAW_BUILTIN_RAISE_NAMES: frozenset[str] = frozenset(
    {
        "AssertionError",
        "Exception",
        "KeyError",
        "NotImplementedError",
        "RuntimeError",
        "TypeError",
        "ValueError",
    }
)
