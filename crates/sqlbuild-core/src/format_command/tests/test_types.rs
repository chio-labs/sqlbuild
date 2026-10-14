use crate::format_command::models::LintReport;

pub(super) struct ReportTestCase {
    pub(super) description: &'static str,
    pub(super) report: LintReport,
    pub(super) expected_text: &'static str,
    pub(super) expected_json: &'static str,
}

pub(super) struct SelectorTestCase {
    pub(super) description: &'static str,
    pub(super) selectors: Vec<String>,
    pub(super) expected_prefixes: Option<Vec<String>>,
    pub(super) expected_partition: (Vec<String>, Vec<String>),
    pub(super) expected_names: Option<Vec<String>>,
}
