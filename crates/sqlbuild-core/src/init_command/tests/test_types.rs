pub(super) struct NameTestCase {
    pub(super) description: &'static str,
    pub(super) directory_name: &'static str,
    pub(super) expected_name: &'static str,
}

pub(super) struct SummaryTestCase {
    pub(super) description: &'static str,
    pub(super) project_name: &'static str,
    pub(super) expected_toml_start: &'static str,
    pub(super) expected_summary_start: &'static str,
}
