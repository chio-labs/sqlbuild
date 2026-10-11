//! `LocalFilesystemComputeLogStorage.prune`: keep the newest complete captures under a file lock.

use std::fs::OpenOptions;
use std::path::{Path, PathBuf};

use crate::compute_logs::_helpers::files::is_symlink;
use crate::compute_logs::_helpers::metadata::{StoredCapture, stored_capture};
use crate::compute_logs::constants::{
    CAPTURE_DATE_HYPHENS, CAPTURE_DATE_LENGTH, COMPLETE_FILE_NAME, METADATA_FILE_NAME,
    PRUNE_LOCK_FILE_NAME,
};

/// Python's `\d{4}-\d{2}-\d{2}\Z` date directory name.
fn is_capture_date(name: &str) -> bool {
    let bytes = name.as_bytes();
    bytes.len() == CAPTURE_DATE_LENGTH
        && bytes.iter().enumerate().all(|(index, byte)| {
            if CAPTURE_DATE_HYPHENS.contains(&index) {
                *byte == b'-'
            } else {
                byte.is_ascii_digit()
            }
        })
}

fn sorted_entries(directory: &Path) -> Option<Vec<PathBuf>> {
    let Ok(listing) = std::fs::read_dir(directory) else {
        return None;
    };
    let mut entries: Vec<PathBuf> = Vec::new();
    for entry in listing {
        let Ok(entry) = entry else {
            return None;
        };
        entries.push(entry.path());
    }
    entries.sort();
    Some(entries)
}

fn file_name(path: &Path) -> String {
    path.file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default()
}

/// Every complete capture as Python's `inventory` lists it, or `None` where it raises.
fn complete_captures(root: &Path) -> Option<Vec<(StoredCapture, PathBuf)>> {
    let mut complete: Vec<(StoredCapture, PathBuf)> = Vec::new();
    for date_directory in sorted_entries(root)? {
        if !is_capture_date(&file_name(&date_directory)) {
            continue;
        }
        if is_symlink(&date_directory) {
            return None;
        }
        if !date_directory.is_dir() {
            continue;
        }
        for capture_directory in sorted_entries(&date_directory)? {
            let name = file_name(&capture_directory);
            if name.starts_with('.') {
                continue;
            }
            if is_symlink(&capture_directory) {
                return None;
            }
            if !capture_directory.is_dir() {
                continue;
            }
            let Ok(json) = std::fs::read_to_string(capture_directory.join(METADATA_FILE_NAME))
            else {
                return None;
            };
            let capture = stored_capture(&json)?;
            if capture.invocation_id != name || capture.capture_date != file_name(&date_directory) {
                return None;
            }
            if capture_directory.join(COMPLETE_FILE_NAME).is_file() {
                complete.push((capture, capture_directory));
            }
        }
    }
    Some(complete)
}

/// Delete all but the `retain` most recently completed captures; any fault leaves them all.
pub(crate) fn prune(root: &Path, retain: usize) {
    let Ok(lock) = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(root.join(PRUNE_LOCK_FILE_NAME))
    else {
        return;
    };
    if lock.lock().is_err() {
        return;
    }
    if let Some(mut complete) = complete_captures(root) {
        complete.sort_by(|left, right| {
            (right.0.order_instant, &right.0.invocation_id)
                .cmp(&(left.0.order_instant, &left.0.invocation_id))
        });
        for (_, directory) in complete.iter().skip(retain) {
            if directory.join(COMPLETE_FILE_NAME).is_file() {
                let _ = std::fs::remove_dir_all(directory);
            }
        }
    }
    let _ = lock.unlock();
}
