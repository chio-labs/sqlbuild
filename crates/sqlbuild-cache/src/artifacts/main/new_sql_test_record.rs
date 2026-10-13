//! The cache record of a newly written SQL test artifact.

use std::fs::Metadata;
use std::path::{Path, PathBuf};

use crate::artifacts::_helpers::sql_test_records::{
    file_sha256, is_safe_relative_sql_path, metadata, mtime_ns, normalized_relative_path,
};
use crate::artifacts::models::SqlTestArtifactRecord;

/// The artifact's record, or `None` when it cannot be read or reused safely.
#[must_use]
pub fn new_sql_test_record(
    tests_root: &Path,
    artifact_path: &Path,
    identity: &str,
) -> Option<SqlTestArtifactRecord> {
    let relative_path: PathBuf = match artifact_path.strip_prefix(tests_root) {
        Ok(relative) => normalized_relative_path(relative),
        Err(_) => return None,
    };
    let metadata: Metadata = metadata(artifact_path)?;
    let content_sha256: String = file_sha256(artifact_path)?;
    if !is_safe_relative_sql_path(&relative_path) {
        return None;
    }
    Some(SqlTestArtifactRecord {
        identity: identity.to_owned(),
        relative_path,
        size: metadata.len(),
        mtime_ns: mtime_ns(&metadata)?,
        content_sha256,
    })
}
