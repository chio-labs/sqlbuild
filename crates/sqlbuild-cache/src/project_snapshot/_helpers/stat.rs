//! The stat fields Python's `os.stat_result` gives a project path, per platform.

use std::fs::Metadata;
use std::path::Path;

use crate::project_snapshot::models::PathStamp;

#[cfg(unix)]
const NANOS: i64 = 1_000_000_000;

/// `(st_mtime_ns, st_ctime_ns)`.
#[cfg(unix)]
pub(crate) fn stat_times(metadata: &Metadata) -> (i64, i64) {
    use std::os::unix::fs::MetadataExt;
    (
        metadata.mtime() * NANOS + metadata.mtime_nsec(),
        metadata.ctime() * NANOS + metadata.ctime_nsec(),
    )
}

/// `(st_mtime_ns, st_ctime_ns)`; Windows reports the creation time as `st_ctime`.
#[cfg(not(unix))]
pub(crate) fn stat_times(metadata: &Metadata) -> (i64, i64) {
    (
        system_time_ns(metadata.modified()),
        system_time_ns(metadata.created()),
    )
}

#[cfg(not(unix))]
fn system_time_ns(time: std::io::Result<std::time::SystemTime>) -> i64 {
    let Ok(time) = time else {
        return 0;
    };
    match time.duration_since(std::time::UNIX_EPOCH) {
        Ok(elapsed) => i64::try_from(elapsed.as_nanos()).unwrap_or(i64::MAX),
        Err(_) => 0,
    }
}

/// `(st_dev, st_ino)`, or `None` where the platform does not expose them stably.
#[cfg(unix)]
pub(crate) fn file_identity(metadata: &Metadata) -> Option<(u64, u64)> {
    use std::os::unix::fs::MetadataExt;
    Some((metadata.dev(), metadata.ino()))
}

/// `(st_dev, st_ino)`, or `None` where the platform does not expose them stably.
#[cfg(not(unix))]
pub(crate) fn file_identity(metadata: &Metadata) -> Option<(u64, u64)> {
    let _ = metadata;
    None
}

/// `os.lstat` identity of one path as a file stamp, or `None` when it is missing.
pub(crate) fn stamp_path(path: &Path) -> Option<PathStamp> {
    let Ok(metadata) = std::fs::symlink_metadata(path) else {
        return None;
    };
    let (mtime_ns, ctime_ns) = stat_times(&metadata);
    Some(PathStamp {
        relative_path: path.to_string_lossy().into_owned(),
        kind: "f",
        size: metadata.len(),
        mtime_ns,
        ctime_ns,
        inode: file_identity(&metadata).map_or(0, |(_, inode)| inode),
        link: None,
    })
}
