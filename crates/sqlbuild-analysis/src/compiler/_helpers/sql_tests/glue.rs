//! Projections of planned SQL tests into the facts the compiler reports.

use std::collections::HashSet;

use crate::compiler::models::SqlTestPlan;

const ERROR_SEVERITY: &str = "error";
const DEFAULT_WORKERS: usize = 4;

/// Each distinct error-severity warning message of one planned test, in warning order.
pub(crate) fn error_messages(plan: &SqlTestPlan) -> Vec<String> {
    let mut seen: HashSet<&str> = HashSet::new();
    plan.warnings
        .iter()
        .filter(|warning| warning.severity == ERROR_SEVERITY)
        .filter(|warning| seen.insert(warning.message.as_str()))
        .map(|warning| warning.message.clone())
        .collect()
}

pub(crate) fn default_workers() -> usize {
    DEFAULT_WORKERS
}

pub(crate) fn default_true() -> bool {
    true
}

pub(crate) fn default_set_difference() -> String {
    "EXCEPT".to_string()
}
