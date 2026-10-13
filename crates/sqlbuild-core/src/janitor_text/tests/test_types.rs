use crate::janitor_text::models::JanitorPlanText;

pub(super) struct ConfirmationTestCase {
    pub(super) description: &'static str,
    pub(super) plan: JanitorPlanText,
    pub(super) expected_prompt: &'static str,
}

pub(super) struct SettingsTestCase {
    pub(super) description: &'static str,
    pub(super) retention_days: i64,
    pub(super) history_versions: i64,
    pub(super) expected_code: Option<&'static str>,
}

pub(super) struct DisabledTestCase {
    pub(super) description: &'static str,
    pub(super) use_color: bool,
    pub(super) expected_text: &'static str,
}
