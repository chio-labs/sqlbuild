//! What janitor will do, and the prompt for its confirmation phrase.

use crate::janitor_text::_helpers::counts::{
    archive_prefix, environment_label, physical_deletion_count,
};
use crate::janitor_text::main::janitor_confirmation_phrase::janitor_confirmation_phrase;
use crate::janitor_text::models::JanitorPlanText;

/// The summary, retention lines and `Type ... to continue: ` prompt.
#[must_use]
pub fn janitor_confirmation_prompt(plan: &JanitorPlanText) -> String {
    let prefix: String = archive_prefix(plan);
    let environment: &str = environment_label(plan);
    let mut text: String = if plan.state_prunes.is_empty() {
        let objects: usize = if plan.direct_mode {
            physical_deletion_count(plan)
        } else {
            plan.candidates.len() + plan.query_artifacts.len()
        };
        format!("Janitor will {prefix}delete {objects} objects from {environment}.\n")
    } else {
        let items: usize = physical_deletion_count(plan) + plan.state_prunes.len();
        format!("Janitor will {prefix}delete {items} items from {environment}.\n")
    };
    if plan.retention_days == 0 {
        text.push_str("Retention: disabled (0 days)\nAge metadata will not be checked.\n");
    } else {
        text.push_str(&format!("Retention: {} days\n", plan.retention_days));
    }
    if plan.direct_mode {
        text.push_str(&format!(
            "Archive retention: {} days\n",
            plan.archive_retention_days
        ));
    }
    text.push_str(&format!(
        "\nType `{}` to continue: ",
        janitor_confirmation_phrase(plan)
    ));
    text
}
