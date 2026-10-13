use crate::cost_report::models::CostRun;

pub(super) struct BreakdownTestCase {
    pub(super) description: &'static str,
    pub(super) run: CostRun,
    pub(super) limit: Option<usize>,
    pub(super) terminal_width: usize,
    pub(super) expected_text: &'static str,
}

pub(super) struct HistoryTestCase {
    pub(super) description: &'static str,
    pub(super) completed_at: &'static str,
    pub(super) expected_text: &'static str,
}
