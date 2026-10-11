//! Load a TOML document the way Python's `tomllib.loads` does.

use crate::constants::BYTE_ORDER_MARK;
use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;

/// The table `tomllib.loads(text)` returns, rejecting TOML 1.1 syntax as `tomllib` does.
pub fn load_toml(text: &str) -> Result<ConfigValue, ConfigError> {
    if text.starts_with(BYTE_ORDER_MARK) {
        return Err(ConfigError::new(
            ConfigErrorKind::Syntax,
            "invalid statement: tomllib does not skip a byte order mark",
        ));
    }
    let text = text.replace("\r\n", "\n");
    let large_integers = crate::toml::_helpers::version::reject_toml_1_1_syntax(&text)?;
    crate::toml::_helpers::namespaces::reject_namespace_conflicts(&text)?;
    if large_integers.is_empty() {
        return crate::toml::_helpers::conversion::parse_document(&text);
    }
    let mark = crate::toml::_helpers::integers::placeholder_mark(&text)?;
    let substituted =
        crate::toml::_helpers::integers::substitute_large_integers(&text, &large_integers, mark);
    crate::toml::_helpers::conversion::parse_document(&substituted).map(|value| {
        crate::toml::_helpers::integers::restore_large_integers(value, &large_integers, mark)
    })
}
