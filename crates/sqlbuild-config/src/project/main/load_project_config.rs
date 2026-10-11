//! Load and validate `sqlbuild_project.toml`.

use crate::project::errors::LoadFailure;
use crate::project::models::{Built, ConfigPaths};

/// `load_project_config`: the validated `ProjectConfig` of `sqlbuild_project.toml`.
pub fn load_project_config(paths: &ConfigPaths) -> Result<Built, LoadFailure> {
    crate::project::_helpers::documents::project_config(paths)
}
