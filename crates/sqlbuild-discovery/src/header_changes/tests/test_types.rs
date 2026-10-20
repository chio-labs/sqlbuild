use crate::header_changes::models::HeaderChange;

pub(super) struct HeaderChangeTestCase {
    pub(super) description: &'static str,
    pub(super) stored_contents: &'static str,
    pub(super) edited_contents: Option<&'static str>,
    pub(super) recorded: bool,
    pub(super) expected_change: HeaderChange,
}

pub(super) struct CustomRuleReadsTestCase {
    pub(super) description: &'static str,
    pub(super) fact_key: Vec<&'static str>,
    pub(super) changed: Vec<&'static str>,
    pub(super) expected_reason: Option<&'static str>,
}
