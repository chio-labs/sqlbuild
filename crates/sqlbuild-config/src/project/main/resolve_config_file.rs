//! Which configuration file a loader reads.

use crate::project::errors::ConfigFailure;
use crate::project::models::{ConfigFile, ConfigPaths};

/// The project or local TOML file, rejecting a legacy YAML file that has no TOML replacement.
pub fn resolve_config_file(paths: &ConfigPaths, local: bool) -> Result<ConfigFile, ConfigFailure> {
    crate::project::_helpers::documents::resolve(paths, local)
}
