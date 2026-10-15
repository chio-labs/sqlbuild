//! `insert_many_sql`: one guarded set-based insert of events into one state table.

/// Rows selected under the first row's column aliases, inserted where the event ID is new.
#[must_use]
pub fn insert_many_sql(table: &str, columns: &[String], rows: &[Vec<String>]) -> String {
    let mut selections: Vec<String> = Vec::with_capacity(rows.len());
    for (index, row) in rows.iter().enumerate() {
        if index > 0 {
            selections.push(format!("SELECT {}", row.join(", ")));
            continue;
        }
        let mut aliased: Vec<String> = Vec::with_capacity(row.len());
        for (literal, column) in row.iter().zip(columns) {
            aliased.push(format!("{literal} AS {column}"));
        }
        selections.push(format!("SELECT {}", aliased.join(", ")));
    }
    let columns: String = columns.join(", ");
    format!(
        "INSERT INTO {table} ({columns}) SELECT {columns} FROM ({}) AS incoming \
WHERE NOT EXISTS (SELECT 1 FROM {table} AS existing WHERE existing.event_id = incoming.event_id)",
        selections.join(" UNION ALL ")
    )
}
