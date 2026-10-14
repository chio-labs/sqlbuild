//! Model migration precedence from live identity and append-only history.

/// Decide a data migration after origin existence and compatibility inspection.
pub fn model_decision(
    destination_exists: bool,
    history: (bool, bool, bool),
    force: bool,
) -> &'static str {
    let (has_event, destination_was_origin, has_fingerprint) = history;
    if !destination_exists {
        "migrate"
    } else if destination_was_origin {
        "superseded_replace"
    } else if !has_event && !has_fingerprint {
        "redo"
    } else if force {
        "forced_replace"
    } else {
        "conflict"
    }
}
