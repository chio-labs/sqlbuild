//! The singular word a change report uses for a node kind.

use crate::definition_changes::_helpers::aspects::kind_words;

/// `model`, `SQL macro`, `source`, or `kind` itself for an unlabelled kind.
#[must_use]
pub fn kind_label(kind: &str) -> &str {
    kind_words(kind).0
}
