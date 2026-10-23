//! The changed nodes a review does not build, such as macros, sources and settings.

use crate::definition_changes::_helpers::aspects::kind_words;
use crate::definition_changes::models::DefinitionChanges;
use crate::review_command::constants::{MODEL_KIND, SEED_KIND};

/// `(kind, name, detail)` of every changed node other than a model or seed.
#[must_use]
pub fn changed_declarations(changes: &DefinitionChanges) -> Vec<(String, String, String)> {
    changes
        .changed
        .values()
        .filter(|change| change.kind != MODEL_KIND && change.kind != SEED_KIND)
        .map(|change| {
            let detail: String = if change.added {
                "added".to_owned()
            } else {
                "changed".to_owned()
            };
            (
                kind_words(&change.kind).0.to_owned(),
                change.name.clone(),
                detail,
            )
        })
        .collect()
}
