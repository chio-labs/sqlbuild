use std::path::{Path, PathBuf};

/// Every staged file's path relative to `staged_dir`.
pub fn staged_files(staged_dir: &Path) -> Vec<PathBuf> {
    crate::artifacts::_helpers::files::staged_files(staged_dir)
        .into_iter()
        .map(|(_, relative)| relative)
        .collect()
}
