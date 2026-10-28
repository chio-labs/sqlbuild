"""Audit execution limits."""

DEFAULT_EVIDENCE_ROW_LIMIT: int = 20
MAX_EVIDENCE_SERIALIZED_BYTES: int = 65_536
DEFAULT_AUDIT_EVIDENCE: str = "warn-and-error"
AUDIT_EVIDENCE_ERROR_ONLY: str = "error"
AUDIT_EVIDENCE_OFF: str = "off"
