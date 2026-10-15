"""Stable Python boundary policy constants."""

POLICY_FILE: str = "python-boundary.toml"
SOURCE_ROOT: str = "src/sqlbuild"
NATIVE_PACKAGE: str = "sqlbuild"
NATIVE_MARKER: str = "native"
SUPPRESS_NAME: str = "suppress"
MODULE_SCOPE: str = "<module>"
STAY_RULES: dict[int, str] = {
    1: "executor or adapter runtime and the shapes it consumes",
    2: "thin shim that invokes user Python",
    3: "public facade",
    4: "glue around a Python-only third-party library",
}
STAY_KEYS: frozenset[str] = frozenset({"path", "rule", "note"})
NOTE_RULE_PATTERN: str = r"\b[Rr]ule (\d+)\b"
ESCAPING_PATH_PARTS: frozenset[str] = frozenset({".", ".."})
