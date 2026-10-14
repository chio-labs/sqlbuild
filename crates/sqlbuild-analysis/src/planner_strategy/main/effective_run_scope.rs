//! The run scope an audit gets after degradation.

use crate::planner_strategy::models::AuditRunScope;

/// Delta-and-final scope only applies to audits attached to incremental or snapshot models.
pub fn effective_run_scope(
    requested: AuditRunScope,
    attached_materialization: Option<&str>,
) -> AuditRunScope {
    if requested == AuditRunScope::Final {
        return AuditRunScope::Final;
    }
    match attached_materialization {
        Some("incremental" | "snapshot") => AuditRunScope::DeltaAndFinal,
        _ => AuditRunScope::Final,
    }
}
