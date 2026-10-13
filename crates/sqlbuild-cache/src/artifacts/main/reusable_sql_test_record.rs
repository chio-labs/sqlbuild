//! Whether a cached SQL test artifact is unchanged and can be kept.

use std::fs::Metadata;
use std::path::{Path, PathBuf};

use crate::artifacts::_helpers::sql_test_records::{
    file_sha256, is_safe_relative_sql_path, metadata, mtime_ns,
};
use crate::artifacts::models::SqlTestArtifactRecord;

/// The record with its artifact's current mtime, when the artifact is unchanged.
#[must_use]
pub fn reusable_sql_test_record(
    tests_root: &Path,
    record: &SqlTestArtifactRecord,
    identity: &str,
) -> Option<SqlTestArtifactRecord> {
    if record.identity != identity || !is_safe_relative_sql_path(&record.relative_path) {
        return None;
    }
    let artifact_path: PathBuf = tests_root.join(&record.relative_path);
    let metadata: Metadata = metadata(&artifact_path)?;
    if !metadata.is_file() || metadata.len() != record.size {
        return None;
    }
    let current_mtime_ns: i64 = mtime_ns(&metadata)?;
    if current_mtime_ns == record.mtime_ns {
        return Some(record.clone());
    }
    if file_sha256(&artifact_path)? != record.content_sha256 {
        return None;
    }
    Some(SqlTestArtifactRecord {
        mtime_ns: current_mtime_ns,
        ..record.clone()
    })
}
