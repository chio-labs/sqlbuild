"""Stable constants for audit rendering."""

from __future__ import annotations

import re

REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
SOURCE_PATTERN: re.Pattern[str] = re.compile(r'__source\("([^"]+)"\)')
BUILT_IN_AUDIT_NAMES: frozenset[str] = frozenset({"not_null", "unique"})
BUILT_IN_AUDIT_SHADOW_CODE: str = "P003"
