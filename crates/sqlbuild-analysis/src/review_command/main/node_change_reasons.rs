//! Why one model or seed counts as changed since the base revision.

use crate::definition_changes::main::selection_reasons::selection_reasons;
use crate::definition_changes::models::{DefinitionChanges, DefinitionSnapshot, ExecutedItem};

/// Why `key` changed: its definition, a declaration it uses, or a source or function it reads.
#[must_use]
pub fn node_change_reasons(
    key: &str,
    (reads, project_wide): (&[String], &[String]),
    (current, changes): (&DefinitionSnapshot, &DefinitionChanges),
) -> Vec<String> {
    let mut declarations: Vec<String> = project_wide.to_vec();
    if let Some(node) = current.nodes.get(key) {
        declarations.extend(node.uses.iter().cloned());
    }
    let item: ExecutedItem = ExecutedItem {
        own_keys: vec![key.to_owned()],
        executed: reads.to_vec(),
        declarations,
        ..ExecutedItem::default()
    };
    selection_reasons(&item, current, changes)
}
