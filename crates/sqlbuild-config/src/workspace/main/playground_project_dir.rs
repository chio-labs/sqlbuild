//! The SQLBuild project directory inside a generated playground.

use std::path::{Path, PathBuf};

use crate::workspace::_helpers::playground::orchestrated;
use crate::workspace::constants::ORCHESTRATED_PROJECT_DIR;

/// `waffle_shop/` under orchestrated playgrounds, else the playground itself.
#[must_use]
pub fn playground_project_dir(target_dir: &Path, template: &str) -> PathBuf {
    if orchestrated(template) {
        return target_dir.join(ORCHESTRATED_PROJECT_DIR);
    }
    target_dir.to_path_buf()
}
