//! A SQL test artifact record read back from the cache file.

use std::path::{Path, PathBuf};

use crate::artifacts::_helpers::sql_test_records::{
    is_safe_relative_sql_path, normalized_relative_path,
};
use crate::artifacts::models::{SqlTestArtifactRecord, StoredSqlTestRecord};

/// The stored record, or `None` when its path could leave the tests directory.
#[must_use]
pub fn stored_sql_test_record(stored: StoredSqlTestRecord) -> Option<SqlTestArtifactRecord> {
    let relative_path: PathBuf = normalized_relative_path(Path::new(&stored.relative_path));
    if !is_safe_relative_sql_path(&relative_path) {
        return None;
    }
    Some(SqlTestArtifactRecord {
        identity: stored.identity,
        relative_path,
        size: stored.size,
        mtime_ns: stored.mtime_ns,
        content_sha256: stored.content_sha256,
    })
}
