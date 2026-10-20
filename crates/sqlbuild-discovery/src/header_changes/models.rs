//! What an edit did to a model header.

use std::collections::BTreeSet;

/// What an edit did to one model's header.
#[derive(Debug, PartialEq, Eq)]
pub enum HeaderChange {
    /// The header's keys and values are unchanged.
    Unchanged,
    /// These keys changed, every one of which the delta recompiles.
    Patched(BTreeSet<String>),
    /// Why the delta cannot recompile this header change.
    Unsupported(String),
    /// The file does not parse; the delta reports its error as a full compile would.
    Unparsed,
}
