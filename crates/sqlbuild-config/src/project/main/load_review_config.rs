//! Read `[review]` from `sqlbuild_project.toml`.

use crate::project::errors::LoadFailure;
use crate::project::models::{ConfigPaths, ReviewConfig};

/// The configured `sqb review` defaults; every field is `None` when `[review]` sets none.
pub fn load_review_config(paths: &ConfigPaths) -> Result<ReviewConfig, LoadFailure> {
    crate::project::_helpers::documents::review_config(paths)
}
