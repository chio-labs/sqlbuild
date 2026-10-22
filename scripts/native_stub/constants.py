"""Stable native stub check constants."""

NATIVE_MODULE: str = "sqlbuild._native"
STUB_PATH: str = "src/sqlbuild/_native.pyi"
TYPING_ONLY_BASES: frozenset[str] = frozenset({"Protocol", "TypedDict"})
PRIVATE_PREFIX: str = "_"
