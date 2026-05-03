"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{([^{}]+)\}")
MACRO_CALL_PATTERN: re.Pattern[str] = re.compile(r"@[A-Za-z_][A-Za-z0-9_]*\s*\(")
