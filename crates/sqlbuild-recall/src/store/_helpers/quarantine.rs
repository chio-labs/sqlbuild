//! The quarantine lock and the checks that keep a corrupt store from being moved aside twice.

use std::fs::{File, OpenOptions};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::store::constants::{QUARANTINE_LOCK_RETRY_MS, QUARANTINE_LOCK_SUFFIX};
use crate::store::errors::{StoreError, StoreErrorKind};
use crate::store::main::observe_store_file::observe_store_file;
use crate::store::models::StoreObservation;

pub(crate) fn moved_name(path: &Path, suffix: &str) -> PathBuf {
    let mut name = path.as_os_str().to_owned();
    name.push(suffix);
    PathBuf::from(name)
}

pub(crate) fn corrupt(path: &Path, doing: &str, error: &std::io::Error) -> StoreError {
    StoreError::new(
        StoreErrorKind::Corrupt,
        format!(
            "cannot {doing} for the corrupt store {}: {error}",
            path.display()
        ),
    )
}

/// One non-blocking attempt at the exclusive `flock`; `Ok(false)` while another process holds it.
#[cfg(unix)]
fn try_lock(file: &File) -> std::io::Result<bool> {
    match rustix::fs::flock(file, rustix::fs::FlockOperation::NonBlockingLockExclusive) {
        Ok(()) => Ok(true),
        Err(rustix::io::Errno::WOULDBLOCK) => Ok(false),
        Err(error) => Err(std::io::Error::from(error)),
    }
}

/// Without `flock`, only the identity re-check guards the move.
#[cfg(not(unix))]
fn try_lock(_file: &File) -> std::io::Result<bool> {
    Ok(true)
}

/// The exclusive lock on `<path>.lock`, waiting until `give_up`; `None` when another process holds it that long.
pub(crate) fn quarantine_lock(path: &Path, give_up: Instant) -> Result<Option<File>, StoreError> {
    let lock_path: PathBuf = moved_name(path, QUARANTINE_LOCK_SUFFIX);
    let file: File = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(&lock_path)
        .map_err(|error| corrupt(path, "open the quarantine lock", &error))?;
    loop {
        match try_lock(&file) {
            Ok(true) => return Ok(Some(file)),
            Ok(false) if Instant::now() < give_up => {
                std::thread::sleep(Duration::from_millis(QUARANTINE_LOCK_RETRY_MS));
            }
            Ok(false) => return Ok(None),
            Err(error) => return Err(corrupt(path, "take the quarantine lock", &error)),
        }
    }
}

/// Whether the file now at `path` is still the one observed corrupt.
pub(crate) fn still_observed(path: &Path, observed: &StoreObservation) -> bool {
    matches!(
        observe_store_file(path),
        Ok(Some(current)) if current.identity == observed.identity
            && (current.header_foreign || !observed.header_foreign)
    )
}
