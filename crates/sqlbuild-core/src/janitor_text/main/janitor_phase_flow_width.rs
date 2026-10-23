//! The width of a janitor phase's action column.

use crate::janitor_text::_helpers::phases::flow;
use crate::janitor_text::models::{JanitorPhase, JanitorPlanText};

/// The widest plain `name` or `name -> destination` the plan's `phase` reports.
#[must_use]
pub fn janitor_phase_flow_width(plan: &JanitorPlanText, phase: JanitorPhase) -> usize {
    let flows: Vec<String> = match phase {
        JanitorPhase::DeleteRelations => plan.candidates.clone(),
        JanitorPhase::Archive => plan
            .archive_candidates
            .iter()
            .map(|candidate| flow(&candidate.name, Some(&candidate.archive_name)))
            .collect(),
        JanitorPhase::DeleteArchives => plan
            .archive_deletions
            .iter()
            .map(|archive| archive.name.clone())
            .collect(),
        JanitorPhase::DropOldNameViews => plan
            .old_name_drops
            .iter()
            .chain(&plan.old_name_missing)
            .map(|view| view.name.clone())
            .collect(),
        JanitorPhase::DropQueryArtifacts => plan.query_artifacts.clone(),
        JanitorPhase::DropReviewSchemas => plan.review_schemas.clone(),
        JanitorPhase::PruneDirectState => plan
            .state_prunes
            .iter()
            .map(|(name, _)| name.clone())
            .collect(),
    };
    flows
        .iter()
        .map(|flow| flow.chars().count())
        .max()
        .unwrap_or(0)
}
