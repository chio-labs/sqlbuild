//! The error message listing selected source tables the warehouse cannot read.

use crate::planner_warehouse::constants::MESSAGE_ITEM_LIMIT;
use crate::planner_warehouse::models::MissingSourceTable;

/// Summarise missing tables, at most ten listed with their readers.
pub fn missing_source_tables_message(missing: &[MissingSourceTable]) -> String {
    let single = missing.len() == 1;
    let noun = if single {
        "source table"
    } else {
        "source tables"
    };
    let verb = if single { "does" } else { "do" };
    let readability = if !missing.iter().any(|item| item.unreadable) {
        ""
    } else if single {
        " or is not readable by the current role"
    } else {
        " or are not readable by the current role"
    };
    let mut lines: Vec<String> = vec![format!(
        "cannot build selected scope: {} {noun} read by selected resources {verb} not exist in the warehouse{readability}:",
        missing.len()
    )];
    for item in missing.iter().take(MESSAGE_ITEM_LIMIT) {
        let suffix = if item.unreadable {
            let role = item.role.as_ref().map_or_else(
                || "the current role".to_owned(),
                |role| format!("role {role}"),
            );
            format!("; the warehouse reports it does not exist or is not readable by {role}")
        } else {
            String::new()
        };
        lines.push(format!(
            "  - source '{}' ({}), read by {}{suffix}",
            item.source_name,
            item.relation,
            item.read_by.join(", ")
        ));
    }
    if missing.len() > MESSAGE_ITEM_LIMIT {
        lines.push(format!(
            "  - ... and {} more",
            missing.len() - MESSAGE_ITEM_LIMIT
        ));
    }
    lines.join("\n")
}
