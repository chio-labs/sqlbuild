//! Live column evidence takes precedence over recorded rename history.

/// Decide a column rename from recorded history and live output evidence.
pub fn column_decision(recorded: bool, live: (bool, bool), still_produced: bool) -> &'static str {
    let (origin, destination) = live;
    if recorded && (destination || !origin) {
        "done"
    } else if still_produced {
        "still_produced"
    } else if origin && !destination {
        "rename"
    } else if !origin && destination {
        "record"
    } else if origin {
        "conflict"
    } else {
        "source_missing"
    }
}
