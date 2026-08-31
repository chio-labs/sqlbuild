"""Janitor constants."""

from __future__ import annotations

from sqlbuild.archives.constants import ARCHIVE_EVENT_TABLE_NAME, ARCHIVE_NAME_PREFIX
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.microbatches.constants import MICROBATCH_TABLE_NAME

BUILT_IN_EXCLUDE_PATTERNS: tuple[str, ...] = (
    FINGERPRINT_TABLE_NAME,
    MICROBATCH_TABLE_NAME,
    SOURCE_FRESHNESS_TABLE_NAME,
    ARCHIVE_EVENT_TABLE_NAME,
    f"{ARCHIVE_NAME_PREFIX}*",
)
