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
    crate::toml::_helpers::version::reject_toml_1_1_syntax(&text)?;
    crate::toml::_helpers::namespaces::reject_namespace_conflicts(&text)?;
    crate::toml::_helpers::conversion::parse_document(&text)
}
