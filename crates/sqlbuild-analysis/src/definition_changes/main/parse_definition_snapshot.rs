//! Read a stored definition snapshot.

use crate::definition_changes::constants::DEFINITION_SNAPSHOT_FORMAT;
use crate::definition_changes::models::DefinitionSnapshot;

/// The snapshot `text` stores, or `None` when it is unreadable or from another format version.
pub fn parse_definition_snapshot(text: &str) -> Option<DefinitionSnapshot> {
    match serde_json::from_str::<DefinitionSnapshot>(text) {
        Ok(snapshot) if snapshot.format == DEFINITION_SNAPSHOT_FORMAT => Some(snapshot),
        Ok(_) | Err(_) => None,
    }
}
