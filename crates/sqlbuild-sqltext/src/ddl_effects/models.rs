//! What one executed statement may have changed in cached relation metadata.

use std::collections::BTreeSet;

/// Cached relation names a statement may have changed; ambiguity changes all of them.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct StatementMetadataEffect {
    /// Invalidation keys of the relations the statement names.
    pub relation_names: BTreeSet<String>,
    /// Every cached relation may have changed.
    pub invalidates_all: bool,
    /// The statement ends the current transaction.
    pub ends_transaction: bool,
}
