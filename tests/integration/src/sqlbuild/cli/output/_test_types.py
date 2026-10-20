"""Test case models for CLI output integration coverage."""

from dataclasses import dataclass

from sqlbuild.compiler.auditing.types import AuditAttachmentKind, AuditOutcome
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind


@dataclass(frozen=True)
class MeasurementEnvelopeTestCase:
    description: str
    outcome: AuditOutcome
    expected_status: str
    expected_passed: bool


@dataclass(frozen=True)
class AttachmentKindEnvelopeTestCase:
    description: str
    attachment_kind: AuditAttachmentKind
    attached_target_kind: AttachedAuditTargetKind | None
    attached_target_name: str | None
    expected_attachment_kind: str
    expected_asset_name: str | None
    expected_degraded: bool = False
    expected_passed: bool = True
