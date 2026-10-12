"""Stable Python boundary policy constants."""

POLICY_FILE: str = "python-boundary.toml"
SOURCE_ROOT: str = "src/sqlbuild"
NATIVE_PACKAGE: str = "sqlbuild"
NATIVE_MARKER: str = "native"
SUPPRESS_NAME: str = "suppress"
MODULE_SCOPE: str = "<module>"
STAY_REASONS: tuple[str, ...] = ("user-code", "adapter", "executor", "public-api")
ESCAPING_PATH_PARTS: frozenset[str] = frozenset({".", ".."})
