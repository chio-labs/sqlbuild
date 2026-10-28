"""Audit evidence setting scope entrypoint."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import Token

from sqlbuild.executor.auditing._helpers.evidence_setting import current_audit_evidence


@contextmanager
def audit_evidence_scope(*, mode: str) -> Iterator[None]:
    """Collect failing audits' evidence rows as the `recall.audit_evidence` `mode` says."""

    token: Token[str] = current_audit_evidence.set(mode)
    try:
        yield
    finally:
        current_audit_evidence.reset(token)
