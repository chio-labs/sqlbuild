use crate::settings::models::RecallSettings;

pub(crate) struct ResolveTestCase {
    pub(crate) description: &'static str,
    pub(crate) files: &'static [(&'static str, &'static str)],
    pub(crate) target: Option<&'static str>,
    pub(crate) expected_settings: RecallSettings,
}

pub(crate) struct ResolveErrorTestCase {
    pub(crate) description: &'static str,
    pub(crate) files: &'static [(&'static str, &'static str)],
    pub(crate) target: Option<&'static str>,
    pub(crate) expected_message_fragment: &'static str,
}
