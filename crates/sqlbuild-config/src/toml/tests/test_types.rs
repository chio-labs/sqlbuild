use crate::errors::ConfigErrorKind;
use crate::models::ConfigValue;

pub(super) struct LoadTomlTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) expected_value: Result<ConfigValue, ConfigErrorKind>,
}

pub(super) struct TomlErrorPositionTestCase {
    pub(super) description: &'static str,
    pub(super) text: String,
    pub(super) expected_position: (Option<usize>, Option<usize>),
}

pub(super) struct HostileTomlTestCase {
    pub(super) description: &'static str,
    pub(super) text: String,
    pub(super) expected_error: ConfigErrorKind,
}

pub(super) struct DeepTomlTestCase {
    pub(super) description: &'static str,
    pub(super) text: String,
    pub(super) expected_value: ConfigValue,
}

pub(super) struct TomlLiteralTestCase {
    pub(super) description: &'static str,
    pub(super) value: crate::toml::models::TomlLiteral,
    pub(super) expected_text: &'static str,
}
