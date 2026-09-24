"""Janitor constants."""

from __future__ import annotations

from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.executor.audit_results.constants import AUDIT_RESULTS_TABLE_NAME
from sqlbuild.executor.janitor_events.constants import JANITOR_EVENTS_TABLE_NAME
from sqlbuild.executor.node_results.constants import NODE_RESULTS_TABLE_NAME
from sqlbuild.microbatches.constants import MICROBATCH_TABLE_NAME

BUILT_IN_EXCLUDE_PATTERNS: tuple[str, ...] = (
    FINGERPRINT_TABLE_NAME,
    MICROBATCH_TABLE_NAME,
    SOURCE_FRESHNESS_TABLE_NAME,
    NODE_RESULTS_TABLE_NAME,
    AUDIT_RESULTS_TABLE_NAME,
    JANITOR_EVENTS_TABLE_NAME,
)

ARCHIVE_NAME_PREFIX: str = "_SQB_ARCHIVE__"
ARCHIVE_NAME_SEPARATOR: str = "__"
ARCHIVE_TIMESTAMP_FORMAT: str = "%Y%m%dT%H%M%SZ"
ARCHIVE_LOOKALIKE_PREFIX: str = "_sqb_archive"
ARCHIVE_ARTIFACT_LABEL: str = "Janitor archive"
MALFORMED_ARCHIVE_REASON: str = (
    "name resembles a janitor archive but does not match the strict archive grammar"
)
