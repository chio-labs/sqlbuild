//! The remedy for selected source tables the warehouse cannot read.

use crate::planner_warehouse::constants::MESSAGE_ITEM_LIMIT;
use crate::planner_warehouse::models::MissingSourceTable;
use std::collections::BTreeSet;

/// Suggest creating, granting or correcting the sources, with their declarations.
pub fn missing_source_tables_help(missing: &[MissingSourceTable]) -> String {
    let locations: Vec<String> = missing
        .iter()
        .take(MESSAGE_ITEM_LIMIT)
        .map(|item| format!("'{}' at {}", item.source_name, item.location))
        .collect();
    let roles: BTreeSet<&str> = missing
        .iter()
        .filter_map(|item| item.role.as_deref())
        .collect();
    let role_text = if roles.is_empty() {
        String::new()
    } else {
        format!(" ({})", roles.into_iter().collect::<Vec<_>>().join(", "))
    };
    let grant = if missing.iter().any(|item| item.unreadable) {
        format!("grant SELECT on it to the role in use{role_text}, ")
    } else {
        String::new()
    };
    format!(
        "create or load the table, {grant}correct its database, schema, or table in the source declaration, or stop reading it from the selected models; declared {}",
        locations.join(", ")
    )
}
