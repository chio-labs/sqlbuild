//! The prune file lock Python's `filelock` takes, and the best-effort prune after a replay.

use std::fs::{File, OpenOptions};
use std::path::Path;

use crate::compute_logs::constants::PRUNE_LOCK_FILE_NAME;
use crate::compute_logs::main::prune_captures::prune_captures;

/// Open or create `<root>/.prune.lock`.
fn open_lock(root: &Path) -> std::io::Result<File> {
    OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(root.join(PRUNE_LOCK_FILE_NAME))
}

/// Python `filelock`'s `fcntl.flock` exclusive lock, released when the file closes.
#[cfg(unix)]
fn lock_exclusive(file: &File) -> std::io::Result<()> {
    rustix::fs::flock(file, rustix::fs::FlockOperation::LockExclusive).map_err(std::io::Error::from)
}

/// Captures are never published here, as in Python, whose directory `fsync` fails on Windows.
#[cfg(not(unix))]
fn lock_exclusive(_file: &File) -> std::io::Result<()> {
    Err(std::io::Error::from(std::io::ErrorKind::Unsupported))
}

/// Hold the exclusive prune lock, retrying when a releasing holder unlinked the file first.
pub(crate) fn acquire_lock(root: &Path) -> std::io::Result<File> {
    loop {
        let file = open_lock(root)?;
        lock_exclusive(&file)?;
        if linked(&file)? {
            return Ok(file);
        }
    }
}

#[cfg(unix)]
fn linked(file: &File) -> std::io::Result<bool> {
    use std::os::unix::fs::MetadataExt;
    Ok(file.metadata()?.nlink() > 0)
}

#[cfg(not(unix))]
fn linked(_file: &File) -> std::io::Result<bool> {
    Ok(true)
}

/// Release the lock as `filelock` does: unlink the file, then close it.
pub(crate) fn release_lock(root: &Path, file: File) {
    let _ = std::fs::remove_file(root.join(PRUNE_LOCK_FILE_NAME));
    drop(file);
}

/// Delete all but the `retain` most recently completed captures; any fault is ignored.
pub(crate) fn prune(root: &Path, retain: usize) {
    let _ = prune_captures(root, Some(retain), &|_| false);
}
