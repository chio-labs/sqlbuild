use std::collections::HashSet;
use std::path::{Path, PathBuf};

use crate::artifacts::errors::ArtifactError;

/// Delete files under `compiled_dir` this compile did not manage, then empty directories.
pub fn remove_stale(
    compiled_dir: &Path,
    managed: &HashSet<PathBuf>,
) -> Result<usize, ArtifactError> {
    crate::artifacts::_helpers::files::remove_stale(compiled_dir, managed)
}
