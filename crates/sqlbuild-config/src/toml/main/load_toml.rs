//! Load a TOML 1.0 document natively.

use crate::errors::ConfigError;
use crate::models::ConfigValue;
use crate::toml::_helpers::reading::load_document;

/// The document's root table, rejecting TOML 1.1 syntax and nesting past the supported depth.
pub fn load_toml(text: &str) -> Result<ConfigValue, ConfigError> {
    load_document(text)
}
