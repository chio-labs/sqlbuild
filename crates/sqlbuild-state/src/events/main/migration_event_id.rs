//! `migration_event_id`: the content-addressed ID of one relation move performed by one run.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::models::JsonValue;

use crate::events::_helpers::identity::{json_digest, optional_text, relation_identity, text};
use crate::events::models::EventRelation;

/// SHA-256 of `[run_id, target_name, origin identity, destination identity]`.
pub fn migration_event_id(
    (run_id, target_name): (&str, Option<&str>),
    origin: &EventRelation,
    destination: &EventRelation,
) -> Result<String, JsonEmitError> {
    let identity = JsonValue::Array(vec![
        text(run_id),
        optional_text(target_name),
        relation_identity(origin),
        relation_identity(destination),
    ]);
    json_digest(&identity, false)
}
