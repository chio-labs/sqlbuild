"""Stable constants for compile-time helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.types import SqlTestMode

MIGRATE_FROM_CONFIG_KEY: str = "migrate_from"


MACRO_CONTEXT_PARAMETER_NAME: str = "ctx"


DEFAULT_SQL_TEST_MODE: SqlTestMode = SqlTestMode.MODEL
