//! The stored JSON form of a definition snapshot.

use crate::definition_changes::constants::DEFINITION_SNAPSHOT_FORMAT;
use crate::definition_changes::models::DefinitionSnapshot;

/// `snapshot` as compact JSON.
pub fn definition_snapshot_json(snapshot: &DefinitionSnapshot) -> String {
    serde_json::to_string(snapshot).unwrap_or_default()
}

/// The snapshot `text` stores, or `None` when it is unreadable or from another format version.
pub fn parse_definition_snapshot(text: &str) -> Option<DefinitionSnapshot> {
    serde_json::from_str::<DefinitionSnapshot>(text)
        .ok()
        .filter(|snapshot| snapshot.format == DEFINITION_SNAPSHOT_FORMAT)
}
