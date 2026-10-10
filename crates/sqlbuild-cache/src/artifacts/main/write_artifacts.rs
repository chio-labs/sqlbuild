use std::path::PathBuf;

use crate::artifacts::errors::ArtifactError;
use crate::artifacts::models::WrittenArtifacts;

/// Write each artifact, leaving a byte-identical existing file untouched when asked to check.
pub fn write_artifacts(
    files: &[(PathBuf, Vec<u8>)],
    check_existing: bool,
) -> Result<WrittenArtifacts, ArtifactError> {
    crate::artifacts::_helpers::files::write_artifacts(files, check_existing)
}
