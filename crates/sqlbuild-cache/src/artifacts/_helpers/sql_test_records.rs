//! File facts of compiled SQL test artifacts: mtimes, content digests and safe paths.

use std::fs::Metadata;
use std::path::{Component, Path, PathBuf};

#[cfg(unix)]
use crate::artifacts::constants::NANOS_PER_SECOND;
use crate::artifacts::constants::SQL_EXTENSION;
use crate::digest::main::sha256_hex::sha256_hex;

/// Python's `os.stat_result.st_mtime_ns`.
#[cfg(unix)]
pub(crate) fn mtime_ns(metadata: &Metadata) -> Option<i64> {
    use std::os::unix::fs::MetadataExt;
    metadata
        .mtime()
        .checked_mul(NANOS_PER_SECOND)?
        .checked_add(metadata.mtime_nsec())
}

/// Python's `os.stat_result.st_mtime_ns`.
#[cfg(not(unix))]
pub(crate) fn mtime_ns(metadata: &Metadata) -> Option<i64> {
    let since = match metadata.modified() {
        Ok(modified) => match modified.duration_since(std::time::UNIX_EPOCH) {
            Ok(since) => since,
            Err(_) => return None,
        },
        Err(_) => return None,
    };
    let Ok(nanos) = i64::try_from(since.as_nanos()) else {
        return None;
    };
    Some(nanos)
}

/// The file's SHA-256 text, or `None` when it cannot be read, as Python's `OSError` is skipped.
pub(crate) fn file_sha256(path: &Path) -> Option<String> {
    match std::fs::read(path) {
        Ok(bytes) => Some(sha256_hex(&bytes)),
        Err(_) => None,
    }
}

/// The file's metadata, or `None` when it cannot be read.
pub(crate) fn metadata(path: &Path) -> Option<Metadata> {
    let Ok(metadata) = std::fs::metadata(path) else {
        return None;
    };
    Some(metadata)
}

/// The path as Python's `PurePath(path)` holds it: without `.` components.
pub(crate) fn normalized_relative_path(path: &Path) -> PathBuf {
    path.components()
        .filter(|component| !matches!(component, Component::CurDir))
        .collect()
}

/// A relative `.sql` path that cannot leave the tests directory.
pub(crate) fn is_safe_relative_sql_path(path: &Path) -> bool {
    !path.is_absolute()
        && !path.has_root()
        && !path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
        && path
            .extension()
            .is_some_and(|extension| extension == SQL_EXTENSION)
}
