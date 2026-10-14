//! `event_read_sql`: every stored event of one state table in history order.

/// `SELECT <columns> FROM <table> ORDER BY created_at, event_id`.
#[must_use]
pub fn event_read_sql(table: &str, columns: &[&str]) -> String {
    format!(
        "SELECT {} FROM {table} ORDER BY created_at, event_id",
        columns.join(", ")
    )
}
