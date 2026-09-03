"""Resource name validation constants."""

from __future__ import annotations

import re

SNAKE_CASE_PATTERN: re.Pattern[str] = re.compile(r"^[a-z](?:[a-z0-9_]*[a-z0-9])?$")
PRIVATE_SNAKE_CASE_PATTERN: re.Pattern[str] = re.compile(r"^_[a-z](?:[a-z0-9_]*[a-z0-9])?$")
UPPERCASE_BOUNDARY_PATTERN: re.Pattern[str] = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
ACRONYM_BOUNDARY_PATTERN: re.Pattern[str] = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
INVALID_CHARACTER_PATTERN: re.Pattern[str] = re.compile(r"[^A-Za-z0-9_]+")
