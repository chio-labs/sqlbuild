//! Whether a janitor plan changes anything.

use crate::janitor_text::models::JanitorPlanText;

/// True when the plan deletes, archives, prunes or drops anything.
#[must_use]
pub fn janitor_plan_has_work(plan: &JanitorPlanText) -> bool {
    (!plan.candidates.is_empty() && !plan.direct_mode)
        || !plan.archive_candidates.is_empty()
        || !plan.archive_deletions.is_empty()
        || !plan.query_artifacts.is_empty()
        || !plan.state_prunes.is_empty()
        || !plan.old_name_drops.is_empty()
        || !plan.old_name_missing.is_empty()
}
