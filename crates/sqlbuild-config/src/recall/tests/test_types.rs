use crate::models::ConfigValue;
use crate::recall::models::RecallSection;

pub(crate) struct ValidSectionTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: ConfigValue,
    pub(crate) expected_section: RecallSection,
}

pub(crate) struct InvalidSectionTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: ConfigValue,
    pub(crate) label: &'static str,
    pub(crate) expected_message_prefix: &'static str,
}
