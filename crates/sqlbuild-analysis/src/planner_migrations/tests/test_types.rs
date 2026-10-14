//! Cases for proof failure and ambiguity handling.

pub(super) struct ProofTestCase {
    pub(super) description: &'static str,
    pub(super) added_names: &'static [&'static str],
    pub(super) proof_result: Result<bool, &'static str>,
    pub(super) expected_pairs: Result<Vec<(String, String)>, &'static str>,
    pub(super) expected_calls: usize,
}
