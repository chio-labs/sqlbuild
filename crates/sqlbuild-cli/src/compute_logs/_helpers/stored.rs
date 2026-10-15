//! Reading captures already on disk: directory identity, inventory and deletion.

use std::path::{Path, PathBuf};

use crate::compute_logs::_helpers::document::{decode_document, validate_document};
use crate::compute_logs::_helpers::paths::{
    ensure_contained, ensure_not_symlink, existing_capture, file_name, is_capture_date,
};
use crate::compute_logs::constants::{
    COMPLETE_FILE_NAME, METADATA_FILE_NAME, PRUNE_LOCK_FILE_NAME,
};
use crate::compute_logs::errors::{ComputeLogError, ComputeLogErrorKind};
use crate::compute_logs::models::{CaptureDocument, InventoryEntry};

/// `_validate_directory_metadata`: the directory names are authoritative for identity and date.
pub(crate) fn validate_directory_document(
    directory: &Path,
    document: &CaptureDocument,
) -> Result<(), ComputeLogError> {
    if document.invocation_id != file_name(directory) {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::Metadata,
            "metadata invocation_id does not match capture directory",
        ));
    }
    let date = directory.parent().map(file_name).unwrap_or_default();
    if document.capture_date != date {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::Metadata,
            "metadata capture_date does not match date directory",
        ));
    }
    Ok(())
}

fn sorted_entries(directory: &Path) -> Result<Vec<PathBuf>, ComputeLogError> {
    let mut entries: Vec<PathBuf> = Vec::new();
    for entry in std::fs::read_dir(directory)? {
        entries.push(entry?.path());
    }
    entries.sort();
    Ok(entries)
}

fn stored_entry(root: &Path, directory: PathBuf) -> Result<InventoryEntry, ComputeLogError> {
    let metadata_path = directory.join(METADATA_FILE_NAME);
    let marker = directory.join(COMPLETE_FILE_NAME);
    ensure_contained(root, &metadata_path)?;
    ensure_contained(root, &marker)?;
    let document = decode_document(&std::fs::read_to_string(&metadata_path)?)?;
    validate_document(&document)?;
    validate_directory_document(&directory, &document)?;
    Ok(InventoryEntry {
        document,
        is_complete: marker.is_file(),
        path: directory,
    })
}

/// `inventory`: every capture under dated directories, ordered by date and invocation id.
pub(crate) fn inventory(root: &Path) -> Result<Vec<InventoryEntry>, ComputeLogError> {
    let mut captures: Vec<InventoryEntry> = Vec::new();
    for date_directory in sorted_entries(root)? {
        let date_name = file_name(&date_directory);
        if date_name == PRUNE_LOCK_FILE_NAME || !is_capture_date(&date_name) {
            continue;
        }
        ensure_not_symlink(&date_directory)?;
        ensure_contained(root, &date_directory)?;
        if !date_directory.is_dir() {
            continue;
        }
        for directory in sorted_entries(&date_directory)? {
            if file_name(&directory).starts_with('.') {
                continue;
            }
            ensure_not_symlink(&directory)?;
            ensure_contained(root, &directory)?;
            if !directory.is_dir() {
                continue;
            }
            captures.push(stored_entry(root, directory)?);
        }
    }
    captures.sort_by(|left, right| {
        (&left.document.capture_date, &left.document.invocation_id)
            .cmp(&(&right.document.capture_date, &right.document.invocation_id))
    });
    Ok(captures)
}

/// `delete`: remove a complete capture no storage instance is writing.
pub(crate) fn delete_inactive(
    root: &Path,
    invocation_id: &str,
    active: bool,
) -> Result<(), ComputeLogError> {
    crate::compute_logs::_helpers::paths::validate_capture_id(invocation_id)?;
    if active {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::State,
            "active captures cannot be deleted",
        ));
    }
    let directory = existing_capture(root, invocation_id)?;
    let marker = directory.join(COMPLETE_FILE_NAME);
    ensure_contained(root, &marker)?;
    if !marker.is_file() {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::State,
            "incomplete captures cannot be deleted",
        ));
    }
    ensure_contained(root, &directory)?;
    std::fs::remove_dir_all(&directory)?;
    Ok(())
}
