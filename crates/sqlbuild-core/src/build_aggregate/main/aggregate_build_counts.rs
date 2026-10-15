//! Aggregate counts and overall status of one build.

use crate::build_aggregate::constants::{
    AUDIT_ERROR, AUDIT_INSUFFICIENT, AUDIT_WARN, FAILED, SKIPPED, SOURCE_FRESHNESS_BLOCKED_CODE,
    SUCCESS, TEST_PASS,
};
use crate::build_aggregate::models::{BuildCounts, BuildResultFacts};

/// Success, failure, skipped, warning and insufficient counts, and whether the build failed.
#[must_use]
pub fn aggregate_build_counts(facts: &BuildResultFacts) -> BuildCounts {
    let mut counts: BuildCounts = BuildCounts::default();
    for model in &facts.models {
        match model.status.as_str() {
            SUCCESS => counts.success += 1,
            FAILED => counts.failure += 1,
            SKIPPED => {
                counts.skipped += 1;
                if model.error_code.as_deref() == Some(SOURCE_FRESHNESS_BLOCKED_CODE) {
                    counts.failure += 1;
                }
            }
            _ => {}
        }
        counts.warning += model.warning_count + matching(&model.audit_outcomes, AUDIT_WARN);
    }
    let statuses = facts
        .seed_statuses
        .iter()
        .chain(facts.functions.iter().map(|(status, _)| status))
        .chain(&facts.load_statuses);
    for status in statuses {
        counts.success += usize::from(status == SUCCESS);
        counts.failure += usize::from(status == FAILED);
        counts.skipped += usize::from(status == SKIPPED);
    }
    counts.warning += facts
        .functions
        .iter()
        .map(|(_, warnings)| warnings)
        .sum::<usize>();
    for outcome in &facts.test_outcomes {
        if outcome == TEST_PASS {
            counts.success += 1;
        } else {
            counts.failure += 1;
        }
    }
    let model_audits = facts.models.iter().flat_map(|model| &model.audit_outcomes);
    counts.insufficient = facts
        .source_audit_outcomes
        .iter()
        .chain(&facts.end_audit_outcomes)
        .chain(model_audits)
        .filter(|outcome| *outcome == AUDIT_INSUFFICIENT)
        .count();
    counts.failure += matching(&facts.source_audit_outcomes, AUDIT_ERROR);
    counts.warning += matching(&facts.source_audit_outcomes, AUDIT_WARN)
        + matching(&facts.end_audit_outcomes, AUDIT_WARN);
    counts.failed = counts.failure > 0
        || facts
            .end_audit_outcomes
            .iter()
            .any(|outcome| outcome == AUDIT_ERROR);
    counts
}

fn matching(outcomes: &[String], expected: &str) -> usize {
    outcomes
        .iter()
        .filter(|outcome| *outcome == expected)
        .count()
}
