//! Merge inferred model columns with declared schema metadata.

use std::collections::HashMap;

use crate::planner_fixtures::models::FixtureColumn;

/// Merge declarations over inferred columns while preserving inferred order.
pub fn merge_metadata(
    inferred: Vec<FixtureColumn>,
    declared: Vec<FixtureColumn>,
) -> Vec<FixtureColumn> {
    let mut order: Vec<String> = Vec::new();
    let mut columns: HashMap<String, FixtureColumn> = HashMap::new();
    for column in inferred {
        order.push(column.folded_name.clone());
        columns.insert(column.folded_name.clone(), column);
    }
    for mut column in declared {
        if let Some(inferred) = columns.get(&column.folded_name) {
            if column.sql_type.as_ref().is_none_or(String::is_empty) {
                column.sql_type.clone_from(&inferred.sql_type);
            }
            if column.nullable.is_none() {
                column.nullable = inferred.nullable;
            }
        } else {
            order.push(column.folded_name.clone());
        }
        columns.insert(column.folded_name.clone(), column);
    }
    order
        .into_iter()
        .filter_map(|name| columns.get(&name).cloned())
        .collect()
}
