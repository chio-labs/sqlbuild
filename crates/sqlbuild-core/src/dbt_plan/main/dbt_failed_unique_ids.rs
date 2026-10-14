//! dbt models whose execution failed or was skipped.

use std::collections::HashMap;

use crate::dbt_plan::constants::SUCCESS_STATUSES;
use crate::dbt_plan::models::DbtExecutedNode;

/// Unsuccessful models, plus the models unsuccessful tests and unit tests depend on.
#[must_use]
pub fn dbt_failed_unique_ids(
    results: &[DbtExecutedNode],
    validation_dependencies: &HashMap<String, Vec<String>>,
) -> Vec<String> {
    let mut failed: Vec<String> = Vec::new();
    for result in results {
        if SUCCESS_STATUSES.contains(&result.status.to_lowercase().as_str()) {
            continue;
        }
        match result.resource_type.as_str() {
            "model" => failed.push(result.unique_id.clone()),
            "test" | "unit_test" => failed.extend(
                validation_dependencies
                    .get(&result.unique_id)
                    .into_iter()
                    .flatten()
                    .cloned(),
            ),
            _ => {}
        }
    }
    failed
}
