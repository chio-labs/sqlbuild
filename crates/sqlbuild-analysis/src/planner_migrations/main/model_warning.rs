//! Ordered model migration diagnostics from the public planning result.

use crate::planner_migrations::constants::{MODEL_CONFLICT, MODEL_DONE, MODEL_RENAMED};
use crate::planner_migrations::models::ModelWarning;

/// Select and format the first applicable model migration diagnostic.
pub fn model_warning(facts: &ModelWarning<'_>) -> Option<(&'static str, String, bool)> {
    let ModelWarning {
        name,
        origin,
        destination,
        decision,
        manual,
        completed,
        target,
        hidden,
        missing,
        deny,
        blocked,
        remedy,
        outcome,
        findings,
    } = facts;
    if *decision == MODEL_DONE || (*decision == MODEL_RENAMED && completed.is_some()) {
        return manual.then(|| ("M101", format!("migration from {origin} completed at {} on target '{target}'; migrate_from can be removed from '{name}'", completed.unwrap_or("unknown time")), false));
    }
    if *hidden {
        return Some((
            "M102",
            format!(
                "model '{name}': migrate_from origin {origin} was built in this target but is not visible; {remedy}"
            ),
            true,
        ));
    }
    if *missing {
        return Some((
            "M102",
            format!(
                "model '{name}': migrate_from origin {origin} does not exist in this target and no recorded migration into it was found; {outcome}"
            ),
            *deny,
        ));
    }
    if *decision == MODEL_CONFLICT {
        return Some((
            "M103",
            format!(
                "migration conflict: {destination} already exists with its own build history and has no recorded migration from {origin}; set migrate_force true to replace it (the replaced table is kept under a _sqb_archive__ name until janitor expires it)"
            ),
            true,
        ));
    }
    blocked.then(|| {
        (
            "M104",
            format!("migration from {origin} is incompatible with '{name}': {findings}"),
            true,
        )
    })
}
