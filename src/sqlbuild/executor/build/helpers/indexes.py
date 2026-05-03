"""Precomputed index construction for build execution."""

from __future__ import annotations

from sqlbuild.compiler.auditing.types import AuditAttachmentKind
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.build.models import BuildIndexes


def build_execution_indexes(plan: PlanOutput) -> BuildIndexes:
    """Build all lookup indexes from a plan output."""

    source_audits: dict[str, list[AuditPlanEntry]] = {}
    model_audits: dict[str, list[AuditPlanEntry]] = {}
    end_audits: list[AuditPlanEntry] = []

    audit: AuditPlanEntry
    for audit in plan.audit_entries:
        if audit.attachment_kind == AuditAttachmentKind.SOURCE:
            source_name: str = audit.attached_target_name or ""
            source_audits.setdefault(source_name, []).append(audit)
        elif audit.attachment_kind == AuditAttachmentKind.MODEL:
            model_name: str = audit.attached_target_name or ""
            model_audits.setdefault(model_name, []).append(audit)
        elif audit.attachment_kind == AuditAttachmentKind.END:
            end_audits.append(audit)

    return BuildIndexes(
        model_entries_by_key={entry.key: entry for entry in plan.model_entries},
        seed_entries_by_key={entry.key: entry for entry in plan.seed_entries},
        test_entries_by_key={entry.key: entry for entry in plan.test_entries},
        source_audits_by_source={k: tuple(v) for k, v in source_audits.items()},
        model_audits_by_model={k: tuple(v) for k, v in model_audits.items()},
        end_audits=tuple(end_audits),
    )
