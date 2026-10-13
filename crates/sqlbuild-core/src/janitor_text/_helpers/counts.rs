//! Counts and labels the janitor confirmation and summary share.

use crate::janitor_text::constants::DEFAULT_ENVIRONMENT;
use crate::janitor_text::models::JanitorPlanText;

/// The plan's target name, or `default`.
pub(crate) fn environment_label(plan: &JanitorPlanText) -> &str {
    plan.target_name.as_deref().unwrap_or(DEFAULT_ENVIRONMENT)
}

/// Warehouse relations the plan drops.
pub(crate) fn physical_deletion_count(plan: &JanitorPlanText) -> usize {
    let relations: usize = if plan.direct_mode {
        plan.archive_deletions.len()
    } else {
        plan.candidates.len()
    };
    relations + plan.query_artifacts.len() + plan.old_name_drops.len()
}

/// `archive N and ` when the plan archives relations.
pub(crate) fn archive_prefix(plan: &JanitorPlanText) -> String {
    if plan.archive_candidates.is_empty() {
        return String::new();
    }
    format!("archive {} and ", plan.archive_candidates.len())
}

/// The connection an `--as` preview inspects through.
pub(crate) fn connection_label(active_target: Option<&str>) -> String {
    active_target.map_or_else(
        || "the active connection".to_owned(),
        |target| format!("the connection of target '{target}'"),
    )
}
