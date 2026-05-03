"""Janitor constants."""

from __future__ import annotations

from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME

BUILT_IN_EXCLUDE_PATTERNS: tuple[str, ...] = (FINGERPRINT_TABLE_NAME,)
