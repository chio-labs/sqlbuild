"""Stable SQL reference patterns."""

from __future__ import annotations

import re

from sqlbuild.compiler.references.types import SqlReferenceKind

REF_CALL_PREFIX: str = rf"{re.escape(SqlReferenceKind.REF.function_name)}\("
SEED_CALL_PREFIX: str = rf"{re.escape(SqlReferenceKind.SEED.function_name)}\("
SOURCE_CALL_PREFIX: str = rf"{re.escape(SqlReferenceKind.SOURCE.function_name)}\("
DBT_REF_CALL_PREFIX: str = rf"{re.escape(SqlReferenceKind.DBT_REF.function_name)}\("
UDF_CALL_PREFIX: str = rf"{re.escape(SqlReferenceKind.UDF.function_name)}\("
TABLE_FUNCTION_CALL_PREFIX: str = rf"{re.escape(SqlReferenceKind.TABLE_FUNCTION.function_name)}\("
_QUOTED_NAME_ARGUMENT: str = r'"([^"]+)"\)'
REF_PATTERN: re.Pattern[str] = re.compile(REF_CALL_PREFIX + _QUOTED_NAME_ARGUMENT)
SEED_PATTERN: re.Pattern[str] = re.compile(SEED_CALL_PREFIX + _QUOTED_NAME_ARGUMENT)
SOURCE_PATTERN: re.Pattern[str] = re.compile(SOURCE_CALL_PREFIX + _QUOTED_NAME_ARGUMENT)
UDF_PATTERN: re.Pattern[str] = re.compile(UDF_CALL_PREFIX + _QUOTED_NAME_ARGUMENT)
TABLE_FUNCTION_PATTERN: re.Pattern[str] = re.compile(
    TABLE_FUNCTION_CALL_PREFIX + _QUOTED_NAME_ARGUMENT
)
