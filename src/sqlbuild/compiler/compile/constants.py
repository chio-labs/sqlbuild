"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{([^{}]+)\}")
