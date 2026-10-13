//! The facts of lifecycle events the terminal index retains, and the index itself.

use std::collections::{HashMap, HashSet};

/// The fields of one lifecycle event that terminal indexing reads.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct TerminalFact {
    pub event_id: String,
    pub event_type: String,
    pub resource_id: Option<String>,
    /// The payload `resource_name`, when it is a string.
    pub resource_name: Option<String>,
    pub resource_attempt_id: Option<String>,
    /// The payload `attempt_number`, when it is an integral number.
    pub attempt_number: Option<i64>,
    /// The payload `operation_name`, when it is a string.
    pub operation_name: Option<String>,
}

/// Which retained resource terminal a claim asks for.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct TerminalRequest {
    pub resource_name: String,
    pub resource_id: Option<String>,
    pub resource_attempt_id: Option<String>,
    pub attempt_number: Option<i64>,
}

/// Lifecycle facts in publication order, with resource terminals awaiting a result claim.
#[derive(Clone, Debug, Default)]
pub struct TerminalIndex {
    /// Retained facts; a fact's position is its event sequence.
    pub(crate) facts: Vec<TerminalFact>,
    pub(crate) sequence_by_event_id: HashMap<String, usize>,
    /// Resource identifiers seen for each resource name, in first-seen order.
    pub(crate) resource_ids_by_name: HashMap<String, Vec<String>>,
    /// Sequences of the resource terminals of each resource identifier.
    pub(crate) pending_by_resource_id: HashMap<String, Vec<usize>>,
    pub(crate) claimed_attempt_ids: HashSet<String>,
}

impl TerminalIndex {
    /// The fact published at `sequence`.
    #[must_use]
    pub fn fact(&self, sequence: usize) -> Option<&TerminalFact> {
        self.facts.get(sequence)
    }

    /// How many facts are retained.
    #[must_use]
    pub fn len(&self) -> usize {
        self.facts.len()
    }

    /// Whether no fact is retained.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.facts.is_empty()
    }
}
