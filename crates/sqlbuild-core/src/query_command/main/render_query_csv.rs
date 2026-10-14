//! Query rows as CSV, as Python's default `csv.writer` writes them.

use crate::query_command::constants::{CSV_DELIMITER, CSV_QUOTE};

fn field(value: &str) -> String {
    if value
        .chars()
        .any(|character| matches!(character, CSV_DELIMITER | CSV_QUOTE | '\n' | '\r'))
    {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_owned()
    }
}

fn record(values: &[String]) -> String {
    if let [only] = values
        && only.is_empty()
    {
        return "\"\"\n".to_owned();
    }
    let fields: Vec<String> = values.iter().map(|value| field(value)).collect();
    format!("{}\n", fields.join(","))
}

/// The header record then one record per row; fields quoted only when they must be.
#[must_use]
pub fn render_query_csv(columns: &[String], rows: &[Vec<String>]) -> String {
    let mut text: String = record(columns);
    for row in rows {
        text.push_str(&record(row));
    }
    text
}
