//! Query rows as a JSON array of objects.

use crate::json::errors::JsonEmitError;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

fn row_object(columns: &[String], row: Vec<JsonValue>) -> JsonValue {
    let mut entries: Vec<(String, JsonValue)> = Vec::new();
    for (column, value) in columns.iter().zip(row) {
        match entries.iter_mut().find(|(name, _)| name == column) {
            Some(entry) => entry.1 = value,
            None => entries.push((column.clone(), value)),
        }
    }
    JsonValue::Object(entries)
}

/// One object per row; a repeated column keeps its first position and its last value.
pub fn render_query_json(
    columns: &[String],
    rows: Vec<Vec<JsonValue>>,
) -> Result<String, JsonEmitError> {
    let objects: Vec<JsonValue> = rows
        .into_iter()
        .map(|row| row_object(columns, row))
        .collect();
    let rendered: String = dumps(
        &JsonValue::Array(objects),
        &JsonDialect::Stdlib(StdlibJsonOptions::new(None)),
    )?;
    Ok(format!("{rendered}\n"))
}
