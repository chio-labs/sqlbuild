"""Canonical resource identity for an attached audit execution."""

from sqlbuild.compiler.auditing.types import AuditAttachmentKind
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind


def audit_resource_id(
    *,
    audit_name: str,
    attachment_kind: AuditAttachmentKind,
    attached_target_kind: AttachedAuditTargetKind | None = None,
    attached_target_name: str | None,
    attached_column_name: str | None,
) -> str:
    """Format the stable execution-protocol identity of one attached audit."""

    identity_kind: str = (
        attached_target_kind.value if attached_target_kind is not None else attachment_kind.value
    )

    parts: tuple[str | None, ...] = (
        "audit",
        audit_name,
        identity_kind,
        attached_target_name,
        attached_column_name,
    )
    return ":".join(filter(None, parts))
