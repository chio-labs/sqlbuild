"""Current audit result projection report entrypoint."""

from sqlbuild.executor.auditing._helpers.result_projection import (
    current_audit_result_projection_impl,
)
from sqlbuild.executor.auditing.models import AuditResultProjection


def current_audit_result_projection() -> AuditResultProjection | None:
    """Return the most recent audit projection report in this execution context."""

    return current_audit_result_projection_impl()
