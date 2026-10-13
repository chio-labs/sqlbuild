use crate::contract_command::models::{ContractProgress, ContractReport};

pub(super) struct ReportTestCase {
    pub(super) description: &'static str,
    pub(super) report: ContractReport,
    pub(super) expected_text: &'static str,
    pub(super) expected_json: &'static str,
    pub(super) expected_exit_code: i32,
}

pub(super) struct MessageTestCase {
    pub(super) description: &'static str,
    pub(super) event: ContractProgress,
    pub(super) expected_message: &'static str,
}
