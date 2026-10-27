//! `query_store`: run one read-only query against a store.

use crate::records::models::RecallValue;
use crate::store::_helpers::sqlite::{checked, from_sql};
use crate::store::errors::{StoreError, StoreErrorKind};
use crate::store::models::{QueryResult, SqliteStore};

/// The columns and at most `limit` rows of `sql`; statements that write are rejected.
pub fn query_store(
    store: &SqliteStore,
    sql: &str,
    limit: Option<usize>,
) -> Result<QueryResult, StoreError> {
    let mut statement = store.connection.prepare(sql).map_err(|error| {
        StoreError::new(
            StoreErrorKind::Query,
            format!("invalid Recall query: {error}"),
        )
    })?;
    if !statement.readonly() {
        return Err(StoreError::new(
            StoreErrorKind::Query,
            "Recall queries must be read-only SELECT statements",
        ));
    }
    let columns: Vec<String> = statement
        .column_names()
        .into_iter()
        .map(str::to_owned)
        .collect();
    let declared: Vec<Option<String>> = statement
        .columns()
        .iter()
        .map(|column| column.decl_type().map(str::to_lowercase))
        .collect();
    let width: usize = columns.len();
    let mut rows = checked(statement.query([]), "run Recall query")?;
    let mut result = QueryResult {
        columns,
        types: Vec::new(),
        rows: Vec::new(),
        truncated: false,
    };
    while let Some(row) = rows.next().map_err(|error| {
        StoreError::new(
            StoreErrorKind::Query,
            format!("Recall query failed: {error}"),
        )
    })? {
        if limit.is_some_and(|limit| result.rows.len() >= limit) {
            result.truncated = true;
            break;
        }
        let mut values = Vec::with_capacity(width);
        for index in 0..width {
            values.push(from_sql(checked(row.get_ref(index), "read Recall row")?));
        }
        result.rows.push(values);
    }
    result.types = declared
        .into_iter()
        .enumerate()
        .map(|(index, declared)| declared.or_else(|| stored_type(&result.rows, index)))
        .collect();
    Ok(result)
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
