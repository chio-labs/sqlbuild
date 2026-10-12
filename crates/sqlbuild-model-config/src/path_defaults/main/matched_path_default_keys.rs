//! `select_path_default(...).matched_keys`: every key matching a model path, sorted.

use crate::errors::ConfigError;
use crate::path_defaults::_helpers::matching::matches_prefix;
use crate::path_defaults::constants::MODELS_PREFIX;
use crate::path_defaults::main::select_path_default::select_path_default;
use crate::path_defaults::models::PathDefaultChoice;

/// The sorted keys matching `model_path`, or the conflict selecting among them raises.
pub fn matched_path_default_keys(
    model_path: &str,
    keys: &[String],
) -> Result<Vec<String>, ConfigError> {
    if let PathDefaultChoice::Conflict(error) = select_path_default(model_path, keys) {
        return Err(error);
    }
    let normalized: String = model_path.replace('\\', "/");
    let normalized: &str = normalized
        .strip_prefix(MODELS_PREFIX)
        .unwrap_or(&normalized);
    let path_parts: Vec<&str> = normalized
        .split('/')
        .filter(|part| !part.is_empty())
        .collect();
    let mut matched: Vec<String> = keys
        .iter()
        .filter(|key| matches_prefix(&path_parts, key))
        .cloned()
        .collect();
    matched.sort();
    Ok(matched)
}
