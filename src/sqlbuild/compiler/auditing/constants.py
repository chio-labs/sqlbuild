"""Stable constants for audit rendering."""

from __future__ import annotations

import re

REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
SEED_PATTERN: re.Pattern[str] = re.compile(r'__seed\("([^"]+)"\)')
SOURCE_PATTERN: re.Pattern[str] = re.compile(r'__source\("([^"]+)"\)')
BUILT_IN_AUDIT_NAMES: frozenset[str] = frozenset(
    {"accepted_values", "not_null", "relationships", "unique"}
)
BUILT_IN_AUDIT_SHADOW_CODE: str = "P003"
