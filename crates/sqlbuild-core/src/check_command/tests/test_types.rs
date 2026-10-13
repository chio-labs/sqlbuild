use crate::check_command::models::{CheckGrouping, CheckResultText, CheckRow};

pub(super) struct GroupTestCase {
    pub(super) description: &'static str,
    pub(super) grouping: CheckGrouping,
    pub(super) expected_label: &'static str,
}

pub(super) struct RowTestCase {
    pub(super) description: &'static str,
    pub(super) row: CheckRow,
    pub(super) use_color: bool,
    pub(super) expected_text: &'static str,
}

pub(super) struct SummaryTestCase {
    pub(super) description: &'static str,
    pub(super) results: Vec<CheckResultText>,
    pub(super) expected_summary: &'static str,
    pub(super) expected_json: &'static str,
    pub(super) expected_exit_code: i32,
}

pub(super) struct SelectionTestCase {
    pub(super) description: &'static str,
    pub(super) non_checks: Vec<String>,
    pub(super) expected_message: Option<&'static str>,
}
