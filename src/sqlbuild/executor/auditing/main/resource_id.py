"""Canonical resource identity for an attached audit execution."""

from sqlbuild.compiler.auditing.types import AuditAttachmentKind


def audit_resource_id(
    *,
    audit_name: str,
    attachment_kind: AuditAttachmentKind,
    attached_target_name: str | None,
    attached_column_name: str | None,
) -> str:
    """Format the stable execution-protocol identity of one attached audit."""

    parts: tuple[str | None, ...] = (
        "audit",
        audit_name,
        attachment_kind.value,
        attached_target_name,
        attached_column_name,
    )
    return ":".join(filter(None, parts))
