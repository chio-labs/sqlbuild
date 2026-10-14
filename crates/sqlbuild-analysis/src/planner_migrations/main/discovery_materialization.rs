//! Stored materialization ownership for automatic migration requests.

/// Check whether a stored definition can transfer history or identity to the current model.
pub fn discovery_materialization(current: &str, metadata: &str) -> bool {
    let stored: serde_json::Value = match serde_json::from_str(metadata) {
        Ok(payload) => payload,
        Err(_) => return false,
    };
    let previous = stored
        .get("config")
        .and_then(|config| config.get("materialized"))
        .and_then(serde_json::Value::as_str);
    matches!(
        (current, previous),
        ("incremental" | "snapshot", Some("incremental" | "snapshot"))
            | ("table" | "view", Some("table" | "view"))
    )
}
