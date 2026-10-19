//! `quarantine_store`: move a corrupt store aside so a fresh one can start.

use std::path::{Path, PathBuf};
use std::time::SystemTime;

use crate::records::main::format_timestamp::format_timestamp;
use crate::store::constants::{COMPANION_SUFFIXES, CORRUPT_SUFFIX};
use crate::store::errors::{StoreError, StoreErrorKind};

fn moved_name(path: &Path, suffix: &str) -> PathBuf {
    let mut name = path.as_os_str().to_owned();
    name.push(suffix);
    PathBuf::from(name)
}

/// Rename `path` and its companion files to `<path>.corrupt-<UTC timestamp>`; returns the new store name.
pub fn quarantine_store(path: &Path, now: SystemTime) -> Result<PathBuf, StoreError> {
    let stamp: String = format_timestamp(now).replace(':', "");
    let suffix: String = format!("{CORRUPT_SUFFIX}{stamp}");
    let target: PathBuf = moved_name(path, &suffix);
    std::fs::rename(path, &target).map_err(|error| {
        StoreError::new(
            StoreErrorKind::Corrupt,
            format!(
                "cannot move the corrupt store {} aside: {error}",
                path.display()
            ),
        )
    })?;
    for companion in COMPANION_SUFFIXES {
        let source: PathBuf = moved_name(path, companion);
        if source.exists() {
            drop(std::fs::rename(&source, moved_name(&target, companion)));
        }
    }
    Ok(target)
}
