"""Stable Python boundary policy constants."""

POLICY_FILE: str = "python-boundary.toml"
SOURCE_ROOT: str = "src/sqlbuild"
NATIVE_MODULE: str = "sqlbuild._native"
NATIVE_PACKAGE: str = "sqlbuild"
NATIVE_NAME: str = "_native"
STAY_REASONS: tuple[str, ...] = ("user-code", "adapter", "executor", "public-api")
