//! `column_migration_event_id`: the content-addressed ID of one column rename by one run.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::models::JsonValue;

use crate::events::_helpers::identity::{json_digest, optional_text, relation_identity, text};
use crate::events::constants::COLUMN_EVENT_TAG;
use crate::events::models::EventRelation;

/// SHA-256 of `["column", run_id, target_name, relation identity, origin, destination]`.
pub fn column_migration_event_id(
    (run_id, target_name): (&str, Option<&str>),
    relation: &EventRelation,
    (origin_column, destination_column): (&str, &str),
) -> Result<String, JsonEmitError> {
    let identity = JsonValue::Array(vec![
        text(COLUMN_EVENT_TAG),
        text(run_id),
        optional_text(target_name),
        relation_identity(relation),
        text(&origin_column.to_lowercase()),
        text(&destination_column.to_lowercase()),
    ]);
    json_digest(&identity, false)
}
