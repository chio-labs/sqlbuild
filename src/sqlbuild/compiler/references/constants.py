"""Stable SQL reference patterns."""

from __future__ import annotations

import re

from sqlbuild.compiler.references._helpers.patterns import quoted_reference_call_pattern
from sqlbuild.compiler.references.types import SqlReferenceKind

REF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.REF)
SEED_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SEED)
SOURCE_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SOURCE)
