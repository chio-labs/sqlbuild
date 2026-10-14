//! Column migration diagnostic codes and explanations.

use crate::planner_migrations::models::ColumnWarning;

/// Format a column migration diagnostic from its decision and display facts.
pub fn column_warning(decision: &str, facts: &ColumnWarning<'_>) -> Option<(&'static str, String)> {
    let ColumnWarning {
        model_name: name,
        relation,
        origin,
        destination: column,
        completed,
        target,
        missing_outcome: outcome,
        message,
    } = facts;
    let declaration = format!("column '{column}' migrate_from {origin}");
    Some(match decision {
        "done" => (
            "M108",
            format!(
                "column rename {origin} -> {column} on {relation} completed at {completed} on target '{target}'; migrate_from can be removed from column '{column}' of '{name}'"
            ),
        ),
        "source_missing" => (
            "M109",
            format!(
                "model '{name}': {declaration}: column {origin} does not exist in {relation} and no recorded rename into {column} was found; {outcome}"
            ),
        ),
        "conflict" => (
            "M110",
            format!(
                "model '{name}': {declaration}: {relation} already has both {origin} and {column}, so the column cannot be renamed in place; drop one of them, or remove migrate_from and let on_schema_change handle the columns"
            ),
        ),
        "still_produced" => (
            "M111",
            format!(
                "model '{name}': {declaration}: the model still produces {origin}; remove it from the query, or remove migrate_from"
            ),
        ),
        "unsupported" => ("M112", format!("model '{name}': {declaration}: {message}")),
        "automatic_unavailable" => (
            "M112",
            format!(
                "column {column} looks renamed from {origin}, but it cannot be renamed in place: {message}; the change follows on_schema_change instead"
            ),
        ),
        _ => return None,
    })
}
