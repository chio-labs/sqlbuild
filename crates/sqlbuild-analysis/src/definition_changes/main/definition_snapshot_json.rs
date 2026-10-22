//! The stored JSON form of a definition snapshot.

use crate::definition_changes::models::DefinitionSnapshot;

/// `snapshot` as compact JSON.
pub fn definition_snapshot_json(snapshot: &DefinitionSnapshot) -> String {
    serde_json::to_string(snapshot).unwrap_or_default()
}
