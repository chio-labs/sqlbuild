//! Whether a cached SQL test artifact is unchanged and can be kept.

use std::fs::Metadata;
use std::path::{Path, PathBuf};

use crate::artifacts::_helpers::sql_test_records::{
    file_sha256, is_safe_relative_sql_path, metadata, mtime_ns,
};
use crate::artifacts::models::{SqlTestArtifactRecord, SqlTestRecordMiss};

/// The record with its artifact's current mtime when the artifact is unchanged, else why not.
pub fn reusable_sql_test_record(
    tests_root: &Path,
    record: &SqlTestArtifactRecord,
    identity: &str,
) -> Result<SqlTestArtifactRecord, SqlTestRecordMiss> {
    if record.identity != identity {
        return Err(SqlTestRecordMiss::IdentityChanged);
    }
    if !is_safe_relative_sql_path(&record.relative_path) {
        return Err(SqlTestRecordMiss::UnsafePath);
    }
    let artifact_path: PathBuf = tests_root.join(&record.relative_path);
    let metadata: Metadata = metadata(&artifact_path)
        .filter(Metadata::is_file)
        .ok_or(SqlTestRecordMiss::ArtifactMissing)?;
    if metadata.len() != record.size {
        return Err(SqlTestRecordMiss::SizeChanged);
    }
    let current_mtime_ns: i64 = mtime_ns(&metadata).ok_or(SqlTestRecordMiss::UnreadableMtime)?;
    if current_mtime_ns == record.mtime_ns {
        return Ok(record.clone());
    }
    if file_sha256(&artifact_path).as_deref() != Some(record.content_sha256.as_str()) {
        return Err(SqlTestRecordMiss::ContentChanged);
    }
    Ok(SqlTestArtifactRecord {
        mtime_ns: current_mtime_ns,
        ..record.clone()
    })
}
