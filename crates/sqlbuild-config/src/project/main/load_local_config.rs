//! Load and validate `sqlbuild_local.toml`.

use crate::project::errors::LoadFailure;
use crate::project::models::{Built, ConfigPaths};

/// `load_local_config`: the validated `LocalConfig`, or the default when the file is absent.
pub fn load_local_config(paths: &ConfigPaths) -> Result<Built, LoadFailure> {
    crate::project::_helpers::documents::local_config(paths)
}
