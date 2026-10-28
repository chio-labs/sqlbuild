//! The types `query_store` reports for a result's columns.

use crate::records::models::RecallValue;

/// Each column's name and declared type, lowercased; `None` for a computed column.
pub(crate) fn column_facts(
    statement: &rusqlite::Statement<'_>,
) -> (Vec<String>, Vec<Option<String>>) {
    statement
        .columns()
        .iter()
        .map(|column| {
            (
                column.name().to_owned(),
                column.decl_type().map(str::to_lowercase),
            )
        })
        .unzip()
}

/// Each column's declared type, or for a computed column the storage class its values share.
pub(crate) fn column_types(
    declared: Vec<Option<String>>,
    rows: &[Vec<RecallValue>],
) -> Vec<Option<String>> {
    declared
        .into_iter()
        .enumerate()
        .map(|(index, declared)| declared.or_else(|| stored_type(rows, index)))
        .collect()
}

/// The storage class every non-NULL value of a computed column holds, as SQLite names it; `None` when they differ or all are NULL.
fn stored_type(rows: &[Vec<RecallValue>], index: usize) -> Option<String> {
    let mut found: Option<&'static str> = None;
    for value in rows.iter().filter_map(|row| row.get(index)) {
        let class: &'static str = match value {
            RecallValue::Null => continue,
            RecallValue::Integer(_) => "integer",
            RecallValue::Real(_) => "real",
            RecallValue::Text(_) => "text",
            RecallValue::Blob(_) => "blob",
        };
        match found {
            None => found = Some(class),
            Some(previous) if previous == class => {}
            Some(_) => return None,
        }
    }
    found.map(str::to_owned)
}
