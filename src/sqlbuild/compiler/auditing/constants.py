"""Stable constants for audit rendering."""

from __future__ import annotations

import re

REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
SOURCE_PATTERN: re.Pattern[str] = re.compile(r'__source\("([^"]+)"\)')
