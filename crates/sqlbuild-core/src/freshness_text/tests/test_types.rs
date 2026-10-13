use crate::freshness_text::models::{FreshnessSourceResult, FreshnessStatus, StateComparison};

pub(super) struct TextTestCase {
    pub(super) description: &'static str,
    pub(super) results: Vec<FreshnessSourceResult>,
    pub(super) use_color: bool,
    pub(super) expected_fragments: &'static [&'static str],
}

pub(super) struct JsonTestCase {
    pub(super) description: &'static str,
    pub(super) results: Vec<FreshnessSourceResult>,
    pub(super) expected_json: &'static str,
}

pub(super) struct ExitCodeTestCase {
    pub(super) description: &'static str,
    pub(super) statuses: &'static [FreshnessStatus],
    pub(super) flags: (bool, bool),
    pub(super) expected_code: i32,
}

pub(super) struct StatusTestCase {
    pub(super) description: &'static str,
    pub(super) comparison: StateComparison,
    pub(super) expected_status: FreshnessStatus,
}
