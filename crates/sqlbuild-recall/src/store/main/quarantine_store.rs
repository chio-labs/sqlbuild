//! `quarantine_store`: move a corrupt store aside, once, so a fresh one can start.

use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime};

use crate::records::main::format_timestamp::format_timestamp;
use crate::store::_helpers::quarantine::{corrupt, moved_name, quarantine_lock, still_observed};
use crate::store::constants::{COMPANION_SUFFIXES, CORRUPT_SUFFIX};
use crate::store::errors::StoreError;
use crate::store::models::{QuarantineOutcome, StoreObservation};

/// Under the store's quarantine lock, rename the observed corrupt file and its companions to `<path>.corrupt-<UTC timestamp>`. When another process already replaced it, keep the store that is there.
pub fn quarantine_store(
    path: &Path,
    observed: &StoreObservation,
    (give_up, now): (Instant, SystemTime),
) -> Result<QuarantineOutcome, StoreError> {
    let Some(lock) = quarantine_lock(path, give_up)? else {
        return Ok(QuarantineOutcome::LockBusy);
    };
    if !still_observed(path, observed) {
        drop(lock);
        return Ok(QuarantineOutcome::Kept);
    }
    let stamp: String = format_timestamp(now).replace(':', "");
    let target: PathBuf = moved_name(path, &format!("{CORRUPT_SUFFIX}{stamp}"));
    for companion in COMPANION_SUFFIXES {
        let source: PathBuf = moved_name(path, companion);
        if source.exists() {
            drop(std::fs::rename(&source, moved_name(&target, companion)));
        }
    }
    let moved = std::fs::rename(path, &target)
        .map(|()| QuarantineOutcome::Moved(target))
        .map_err(|error| corrupt(path, "move the file aside", &error));
    drop(lock);
    moved
}
