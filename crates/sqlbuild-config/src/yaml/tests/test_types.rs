use crate::errors::ConfigErrorKind;
use crate::models::ConfigValue;

pub(super) struct SafeLoadTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) expected_value: Result<ConfigValue, ConfigErrorKind>,
}

pub(super) struct HostileYamlTestCase {
    pub(super) description: &'static str,
    pub(super) text: String,
    pub(super) expected_error: ConfigErrorKind,
}
