"""Stable constants for discovery helpers."""

from __future__ import annotations

import re

MODEL_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*MODEL\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)

TEST_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*TEST\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)

TEST_HEADER_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*TEST\s*\((?P<header>.*?)\)\s*;\s*",
    re.DOTALL | re.MULTILINE,
)

AUDIT_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*AUDIT\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)

AUDIT_HEADER_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*AUDIT\s*\((?P<header>.*?)\)\s*;\s*",
    re.DOTALL | re.MULTILINE,
)

FUNCTION_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*FUNCTION\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)
