//! Load one YAML 1.2 document with the core schema and merge keys.

use crate::errors::ConfigError;
use crate::models::ConfigValue;

/// The value of the single document in `text`; an empty stream is `Null`.
pub fn safe_load(text: &str) -> Result<ConfigValue, ConfigError> {
    let text = crate::yaml::_helpers::reader::without_byte_order_mark(text);
    crate::yaml::_helpers::reader::check_characters(text)?;
    let document = crate::yaml::_helpers::composer::compose(text)?;
    crate::yaml::_helpers::constructor::construct_document(&document, text.chars().count())
}
