//! The exact phrase that confirms a janitor plan.

use crate::janitor_text::_helpers::counts::{
    archive_prefix, environment_label, physical_deletion_count,
};
use crate::janitor_text::models::JanitorPlanText;

/// `[archive N and ]delete M objects|items from <target>`.
#[must_use]
pub fn janitor_confirmation_phrase(plan: &JanitorPlanText) -> String {
    let prefix: String = archive_prefix(plan);
    let deletions: usize = physical_deletion_count(plan);
    if plan.state_prunes.is_empty() {
        return format!(
            "{prefix}delete {deletions} objects from {}",
            environment_label(plan)
        );
    }
    format!(
        "{prefix}delete {} items from {}",
        deletions + plan.state_prunes.len(),
        environment_label(plan)
    )
}
