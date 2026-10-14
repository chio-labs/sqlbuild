//! Plan reasons of a model's own change.

use crate::planner_strategy::models::{ChangeFacts, PlanChangeKind, PlanReason};

/// The reason of a first run or a definition change; `None` for renames and no change.
pub(crate) fn own_change_reason(kind: PlanChangeKind) -> Option<PlanReason> {
    match kind {
        PlanChangeKind::FirstRun => Some(PlanReason::FirstRun),
        PlanChangeKind::QueryChanged => Some(PlanReason::QueryChanged),
        PlanChangeKind::FunctionChanged => Some(PlanReason::FunctionChanged),
        PlanChangeKind::ConfigChanged => Some(PlanReason::ConfigChanged),
        PlanChangeKind::SchemaChanged => Some(PlanReason::SchemaChanged),
        PlanChangeKind::Renamed | PlanChangeKind::NoChange => None,
    }
}

/// The reason a full backfill rebuilds the table.
pub(crate) fn backfill_reason(change: &ChangeFacts) -> PlanReason {
    if change.query_changed {
        PlanReason::QueryChanged
    } else if !change.changed_functions.is_empty() {
        PlanReason::FunctionChanged
    } else if change.config_changed {
        PlanReason::ConfigChanged
    } else if !change.schema_findings.is_empty() {
        PlanReason::SchemaChanged
    } else {
        PlanReason::FullRefresh
    }
}
