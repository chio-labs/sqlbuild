//! Resolve and create the configured compute log root, as the storage constructor does.

use std::path::{Path, PathBuf};

use crate::compute_logs::_helpers::files::is_symlink;
use crate::compute_logs::constants::DEFAULT_LOG_DIRECTORY;
use crate::compute_logs::errors::{ComputeLogError, ComputeLogErrorKind};

fn symlink_root() -> ComputeLogError {
    ComputeLogError::rejected(
        ComputeLogErrorKind::Path,
        "configured compute log root cannot be a symlink",
    )
}

/// The resolved root, `<project_dir>/logs` unless `root` is given; rejects symlinks and files.
pub fn open_log_root(
    project_dir: &Path,
    root: Option<&Path>,
    retention_count: Option<i64>,
) -> Result<PathBuf, ComputeLogError> {
    if retention_count.is_some_and(|count| count < 0) {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::InvalidLimit,
            "retention_count must be nonnegative or None",
        ));
    }
    let configured: PathBuf = root.map_or_else(
        || project_dir.join(DEFAULT_LOG_DIRECTORY),
        Path::to_path_buf,
    );
    if is_symlink(&configured) {
        return Err(symlink_root());
    }
    std::fs::create_dir_all(&configured)?;
    if is_symlink(&configured) {
        return Err(symlink_root());
    }
    let resolved = std::fs::canonicalize(&configured)?;
    if !resolved.is_dir() {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::Path,
            "compute log root must be a directory",
        ));
    }
    Ok(resolved)
}
