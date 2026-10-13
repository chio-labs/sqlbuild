//! The message shown while warehouse connections open.

/// `Connecting to <adapter>...`, with the connection count when there are several.
#[must_use]
pub fn connection_start_message(adapter_name: &str, connection_count: i64) -> String {
    if connection_count <= 1 {
        return format!("Connecting to {adapter_name}...");
    }
    format!("Connecting to {adapter_name} ({connection_count} connections)...")
}
