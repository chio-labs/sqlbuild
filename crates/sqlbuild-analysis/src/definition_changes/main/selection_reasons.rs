//! Why a test or scenario is affected by the changes since the base revision.

use crate::definition_changes::_helpers::reasons::{
    declaration_reason, executed_reason, own_reason, reached_declarations,
};
use crate::definition_changes::models::{DefinitionChanges, DefinitionSnapshot, ExecutedItem};

/// One reason per changed dependency of `item`, own definition first; empty when nothing changed.
pub fn selection_reasons(
    item: &ExecutedItem,
    current: &DefinitionSnapshot,
    changes: &DefinitionChanges,
) -> Vec<String> {
    let mut reasons: Vec<String> = Vec::new();
    let mut push = |reason: String| {
        if !reasons.contains(&reason) {
            reasons.push(reason);
        }
    };
    for key in &item.own_keys {
        if let Some(change) = changes.changed.get(key) {
            push(own_reason(change));
        }
    }
    for key in &item.executed {
        if let Some(change) = changes.changed.get(key) {
            push(executed_reason(change));
        }
    }
    for key in reached_declarations(item, current) {
        if let Some(change) = changes.changed.get(&key) {
            push(declaration_reason(change));
        }
    }
    reasons
}
