use crate::seed_command::models::SeedRow;

pub(super) struct ReadyTestCase {
    pub(super) description: &'static str,
    pub(super) names: Vec<String>,
    pub(super) expected_text: &'static str,
}

pub(super) struct RowTestCase {
    pub(super) description: &'static str,
    pub(super) row: SeedRow,
    pub(super) expected_text: &'static str,
}

pub(super) struct CompletionTestCase {
    pub(super) description: &'static str,
    pub(super) counts: (usize, usize, usize),
    pub(super) expected_text: &'static str,
    pub(super) expected_exit_code: i32,
}
