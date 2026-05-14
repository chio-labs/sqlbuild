"""Stable constants for audit rendering."""

from __future__ import annotations

import re

from sqlbuild.shared.helpers.sql_reference_patterns import quoted_reference_call_pattern
from sqlbuild.shared.types import SqlReferenceKind

REF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.REF)
SEED_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SEED)
SOURCE_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SOURCE)
BUILT_IN_AUDIT_NAMES: frozenset[str] = frozenset(
    {"accepted_values", "not_null", "relationships", "unique"}
)
BUILT_IN_AUDIT_SHADOW_CODE: str = "P003"
