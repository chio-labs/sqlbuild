//! Read a TOML 1.0 document natively.

use crate::constants::BYTE_ORDER_MARK;
use crate::errors::ConfigError;
use crate::models::ConfigValue;
use crate::toml::_helpers::conversion::parse_document;
use crate::toml::_helpers::version::reject_toml_1_1_syntax;

/// The document's root table; a leading byte order mark is ignored, as editors add one.
pub(crate) fn load_document(text: &str) -> Result<ConfigValue, ConfigError> {
    let text = text
        .strip_prefix(BYTE_ORDER_MARK)
        .unwrap_or(text)
        .replace("\r\n", "\n");
    reject_toml_1_1_syntax(&text)?;
    parse_document(&text)
}
