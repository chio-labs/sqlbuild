"""Query change detection by hash comparison."""

from __future__ import annotations

from sqlbuild.compiler.fingerprints.models import Fingerprint


def detect_query_change(
    *,
    compiled_query_hash: str,
    fingerprint: Fingerprint,
) -> bool:
    """Compare compiled hashes against the stored fingerprint to detect query changes."""

    return compiled_query_hash != fingerprint.definition_hash
