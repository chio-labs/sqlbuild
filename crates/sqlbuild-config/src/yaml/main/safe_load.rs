//! Load one YAML document the way PyYAML's `yaml.safe_load` does.

use crate::errors::ConfigError;
use crate::models::ConfigValue;

/// The value `yaml.safe_load(text)` returns, with YAML 1.1 implicit typing and merge keys.
pub fn safe_load(text: &str) -> Result<ConfigValue, ConfigError> {
    let text = crate::yaml::_helpers::reader::without_byte_order_mark(text);
    crate::yaml::_helpers::reader::check_characters(text)?;
    let document = crate::yaml::_helpers::composer::compose(text)?;
    crate::yaml::_helpers::constructor::construct_document(&document, text.chars().count())
}
