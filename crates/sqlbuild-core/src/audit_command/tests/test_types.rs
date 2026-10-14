use crate::audit_command::models::AuditCounts;

pub(super) struct HeaderTestCase {
    pub(super) description: &'static str,
    pub(super) counts: (usize, usize),
    pub(super) expected_text: &'static str,
}

pub(super) struct SummaryTestCase {
    pub(super) description: &'static str,
    pub(super) counts: AuditCounts,
    pub(super) expected_text: &'static str,
    pub(super) expected_exit_code: i32,
}
