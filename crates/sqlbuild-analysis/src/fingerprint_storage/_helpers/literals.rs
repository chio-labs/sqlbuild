//! SQL string literals for fingerprint rows.

/// `'value'` with single quotes doubled.
pub(crate) fn string_literal(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

/// `NULL`, or the quoted literal.
pub(crate) fn optional_string_literal(value: Option<&str>) -> String {
    value.map_or_else(|| "NULL".to_owned(), string_literal)
}

/// `'a', 'b'` for an `IN` list.
pub(crate) fn literal_list(values: &[String]) -> String {
    values
        .iter()
        .map(|value| string_literal(value))
        .collect::<Vec<String>>()
        .join(", ")
}
