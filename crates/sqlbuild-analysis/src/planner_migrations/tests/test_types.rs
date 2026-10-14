//! Cases for proof failure and ambiguity handling.

pub(super) struct ProofTestCase {
    pub(super) description: &'static str,
    pub(super) added_names: &'static [&'static str],
    pub(super) proof_result: Result<bool, &'static str>,
    pub(super) expected_pairs: Result<Vec<(String, String)>, &'static str>,
    pub(super) expected_calls: usize,
}
pub(super) struct CompatibilityTestCase {
    pub description: &'static str,
    pub expected_type: &'static str,
    pub actual_type: &'static str,
    pub snapshot: bool,
    pub policy: &'static str,
    pub expected_findings: &'static [&'static str],
}

pub(super) struct MigrationMatchTestCase {
    pub description: &'static str,
    pub hashes: &'static [&'static str],
    pub candidates: &'static [(&'static str, &'static str)],
    pub expected_matches: &'static [(usize, usize)],
    pub expected_ambiguous: usize,
}
#[derive(Debug)]
pub(super) struct ColumnDecisionTestCase {
    pub description: &'static str,
    pub recorded: bool,
    pub live: (bool, bool),
    pub still_produced: bool,
    pub expected_decision: &'static str,
}
pub(super) struct ModelDecisionTestCase {
    pub description: &'static str,
    pub destination_exists: bool,
    pub history: (bool, bool, bool),
    pub force: bool,
    pub expected_decision: &'static str,
}
