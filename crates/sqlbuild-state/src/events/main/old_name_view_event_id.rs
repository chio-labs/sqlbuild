//! `old_name_view_event_id`: the content-addressed ID of one old-name step of a recorded move.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::models::JsonValue;

use crate::events::_helpers::identity::{json_digest, text};
use crate::events::constants::OLD_NAME_EVENT_TAG;

/// SHA-256 of `["old_name", event_type, migration_event_id]`.
pub fn old_name_view_event_id(
    event_type: &str,
    migration_event_id: &str,
) -> Result<String, JsonEmitError> {
    let identity = JsonValue::Array(vec![
        text(OLD_NAME_EVENT_TAG),
        text(event_type),
        text(migration_event_id),
    ]);
    json_digest(&identity, false)
}
