//! Load one in-memory YAML document as a discovered file would load.

use crate::models::{DiscoveryFailure, FailureKind};
use crate::yaml_files::_helpers::failures::yaml_failure;
use sqlbuild_config::models::ConfigValue;
use sqlbuild_config::yaml::main::safe_load::safe_load;

/// The document's value, or the failure raised as `kind` naming `file_path`.
pub fn load_yaml_text(
    file_path: &str,
    text: &str,
    kind: FailureKind,
) -> Result<ConfigValue, DiscoveryFailure> {
    safe_load(text).map_err(|error| yaml_failure(file_path, kind, error))
}
