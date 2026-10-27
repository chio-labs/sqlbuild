use crate::query_command::models::QueryDisplay;

/// Owned copies of string literals.
pub(super) fn texts(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// A small invocation-count result with one NULL count.
pub(super) fn invocations() -> QueryDisplay {
    QueryDisplay {
        columns: texts(&["status", "origin", "invocations"]),
        types: vec![
            Some("varchar".to_owned()),
            Some("varchar".to_owned()),
            Some("int32".to_owned()),
        ],
        numeric: vec![false, false, true],
        rows: vec![
            texts(&["completed", "integration", "133"]),
            texts(&["cancelled", "local", "NULL"]),
        ],
        truncated: false,
        limit: None,
    }
}
