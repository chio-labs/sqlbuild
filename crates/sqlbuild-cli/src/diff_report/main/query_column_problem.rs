//! Preflight checks of the columns one raw diff query returns.

use crate::diff_report::errors::DiffUserError;

/// No columns (C237), duplicate names ignoring case (C238), or too many columns (C239).
pub fn query_column_problem(
    label: &str,
    columns: &[String],
    max_columns: Option<i64>,
) -> Result<(), DiffUserError> {
    let display: String = if label.to_lowercase().ends_with("query") {
        label.to_owned()
    } else {
        format!("{label} query")
    };
    if columns.is_empty() {
        return Err(DiffUserError {
            message: format!("{display} returned no columns"),
            code: "C237".to_owned(),
            help: None,
        });
    }
    let lowered: Vec<String> = columns.iter().map(|column| column.to_lowercase()).collect();
    let mut sorted: Vec<&String> = lowered.iter().collect();
    sorted.sort();
    let mut duplicates: Vec<&String> = Vec::new();
    for pair in sorted.windows(2) {
        if pair[0] == pair[1] {
            duplicates.push(pair[0]);
        }
    }
    duplicates.sort();
    duplicates.dedup();
    if !duplicates.is_empty() {
        let names: Vec<&str> = duplicates.into_iter().map(String::as_str).collect();
        return Err(DiffUserError {
            message: format!(
                "{display} returns duplicate column names: {}",
                names.join(", ")
            ),
            code: "C238".to_owned(),
            help: Some("add unique aliases before comparing query results".to_owned()),
        });
    }
    match max_columns {
        Some(limit) if columns.len() as i64 > limit => Err(DiffUserError {
            message: format!(
                "{display} has {} columns, exceeding --max-columns {limit}",
                columns.len()
            ),
            code: "C239".to_owned(),
            help: None,
        }),
        _ => Ok(()),
    }
}
