"""A compiled audit as a `CompiledAudit` record, for callers that copy or expose it."""

from sqlbuild.compiler.compile.models import CompiledAudit
from sqlbuild.compiler.compile.types import CompiledAuditView
from sqlbuild.compiler.compiled_project._helpers.model_updates import compiled_audit_record_impl


def compiled_audit_record(audit: CompiledAuditView) -> CompiledAudit:
    """The audit as a `CompiledAudit`, projected from its owner when it is a native view."""

    return compiled_audit_record_impl(audit)
