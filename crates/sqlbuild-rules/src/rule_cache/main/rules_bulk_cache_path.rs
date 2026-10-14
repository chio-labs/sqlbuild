//! Where one bulk Rules cache file lives, namespaced by the native compiler engine.

use std::path::{Path, PathBuf};

use crate::rule_cache::constants::{BULK_DIRECTORY, RULES_CACHE_DIRECTORY, TARGET_DIRECTORY};

/// `<project>/target/rules-cache-native-v1/bulk/<file_name>`.
pub fn rules_bulk_cache_path(project_dir: &Path, file_name: &str) -> PathBuf {
    project_dir
        .join(TARGET_DIRECTORY)
        .join(RULES_CACHE_DIRECTORY)
        .join(BULK_DIRECTORY)
        .join(file_name)
}
