//! Read `[git] base_ref` from `sqlbuild_project.toml`.

use crate::project::errors::LoadFailure;
use crate::project::models::ConfigPaths;

/// The configured base ref that `--since @base` names, or `None` when `[git]` sets none.
pub fn load_git_base_ref(paths: &ConfigPaths) -> Result<Option<String>, LoadFailure> {
    crate::project::_helpers::documents::git_base_ref(paths)
}
