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

pub(super) struct ComposeMarksTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    /// `(start, end, value)` of every scalar, sorted, as PyYAML 6 marks them.
    pub(super) expected_scalars: Result<&'static [(usize, usize, &'static str)], ConfigErrorKind>,
}
