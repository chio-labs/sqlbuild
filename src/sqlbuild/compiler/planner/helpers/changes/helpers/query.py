"""Query change detection by hash comparison."""

from __future__ import annotations

from sqlbuild.compiler.fingerprints.models import Fingerprint


def detect_query_change(
    *,
    compiled_query_hash: str,
    compiled_ast_hash: str | None,
    fingerprint: Fingerprint,
    sqlglot_enabled: bool,
) -> bool:
    """Compare compiled hashes against the stored fingerprint to detect query changes."""

    if sqlglot_enabled and compiled_ast_hash is not None and fingerprint.ast_hash is not None:
        return compiled_ast_hash != fingerprint.ast_hash
    return compiled_query_hash != fingerprint.query_hash
