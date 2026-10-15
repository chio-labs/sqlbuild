//! `existing_event_ids_sql`: the lookup of event IDs already stored before a bulk insert.

/// `SELECT event_id FROM <table> WHERE event_id IN (<literals>)`.
#[must_use]
pub fn existing_event_ids_sql(table: &str, event_id_literals: &[String]) -> String {
    format!(
        "SELECT event_id FROM {table} WHERE event_id IN ({})",
        event_id_literals.join(", ")
    )
}
