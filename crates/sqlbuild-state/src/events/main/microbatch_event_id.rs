//! `microbatch_event_id`: the content-addressed ID of one logical microbatch event.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::models::JsonValue;

use crate::events::_helpers::identity::{json_digest, optional_text, text};
use crate::microbatches::models::MicrobatchEventIdentity;

/// SHA-256 of the compact, ASCII-escaped JSON array of the identity fields.
pub fn microbatch_event_id(identity: &MicrobatchEventIdentity) -> Result<String, JsonEmitError> {
    let value = JsonValue::Array(vec![
        text(&identity.scope_kind),
        text(&identity.scope_key),
        text(&identity.model_name),
        optional_text(identity.target_database.as_deref()),
        optional_text(identity.target_schema.as_deref()),
        text(&identity.target_name),
        text(&identity.physical_generation_id),
        text(&identity.record_type),
        optional_text(identity.partition_start.as_deref()),
        optional_text(identity.partition_end.as_deref()),
        text(&identity.completion_reason),
    ]);
    json_digest(&value, false)
}
