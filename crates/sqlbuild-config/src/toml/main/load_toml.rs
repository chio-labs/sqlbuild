//! Load a TOML document the way Python's `tomllib.loads` does.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;
use crate::toml::_helpers::reading::{bracket_depth, load_document};
use crate::toml::constants::{DEEP_DOCUMENT_BRACKETS, DEEP_DOCUMENT_STACK_BYTES};

/// The table `tomllib.loads(text)` returns, rejecting TOML 1.1 syntax as `tomllib` does.
pub fn load_toml(text: &str) -> Result<ConfigValue, ConfigError> {
    if bracket_depth(text) <= DEEP_DOCUMENT_BRACKETS {
        return load_document(text);
    }
    std::thread::scope(|scope| {
        std::thread::Builder::new()
            .stack_size(DEEP_DOCUMENT_STACK_BYTES)
            .spawn_scoped(scope, || load_document(text))
            .map_err(|error| ConfigError::new(ConfigErrorKind::Unsupported, error.to_string()))?
            .join()
            .unwrap_or_else(|_| {
                Err(ConfigError::new(
                    ConfigErrorKind::Unsupported,
                    "the deep TOML reader stopped unexpectedly",
                ))
            })
    })
}
