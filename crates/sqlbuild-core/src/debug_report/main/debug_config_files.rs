//! The project and local config files of a project directory.

use std::path::{Path, PathBuf};

use crate::constants::PROJECT_CONFIG_FILENAME;
use crate::debug_report::constants::{
    LEGACY_LOCAL_CONFIG_FILENAME, LEGACY_PROJECT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME,
};
use crate::debug_report::models::DebugConfigFiles;

fn existing_path(project_dir: &Path, preferred: &str, legacy: &str) -> PathBuf {
    let preferred_path: PathBuf = project_dir.join(preferred);
    if preferred_path.exists() {
        return preferred_path;
    }
    let legacy_path: PathBuf = project_dir.join(legacy);
    if legacy_path.exists() {
        return legacy_path;
    }
    preferred_path
}

/// The preferred config files, or their legacy YAML names when only those exist.
#[must_use]
pub fn debug_config_files(project_dir: &Path) -> DebugConfigFiles {
    let local_path: PathBuf = existing_path(
        project_dir,
        LOCAL_CONFIG_FILENAME,
        LEGACY_LOCAL_CONFIG_FILENAME,
    );
    DebugConfigFiles {
        project_file: existing_path(
            project_dir,
            PROJECT_CONFIG_FILENAME,
            LEGACY_PROJECT_CONFIG_FILENAME,
        ),
        local_file: local_path.exists().then_some(local_path),
    }
}
