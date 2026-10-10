use std::collections::HashSet;
use std::path::{Path, PathBuf};

use crate::artifacts::errors::ArtifactError;
use crate::artifacts::models::Publication;

/// Publish the expected staged files, moving the whole tree when no compiled directory exists.
pub fn publish_staged(
    staged_dir: &Path,
    compiled_dir: &Path,
    expected: &HashSet<PathBuf>,
) -> Result<Publication, ArtifactError> {
    crate::artifacts::_helpers::files::publish_staged(staged_dir, compiled_dir, expected)
}
