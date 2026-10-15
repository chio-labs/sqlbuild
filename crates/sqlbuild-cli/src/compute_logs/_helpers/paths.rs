//! Capture identities, date directory names, symlink rejection and root containment.

use std::path::{Path, PathBuf};

use crate::compute_logs::_helpers::files::is_symlink;
use crate::compute_logs::constants::{
    CAPTURE_DATE_HYPHENS, CAPTURE_DATE_LENGTH, MAX_CAPTURE_ID_LENGTH, MAX_READ_BYTES,
};
use crate::compute_logs::errors::{ComputeLogError, ComputeLogErrorKind};

/// Python's `[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z` capture identity.
pub(crate) fn validate_capture_id(invocation_id: &str) -> Result<(), ComputeLogError> {
    let bytes = invocation_id.as_bytes();
    let valid = !bytes.is_empty()
        && bytes.len() <= MAX_CAPTURE_ID_LENGTH
        && bytes[0].is_ascii_alphanumeric()
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || *byte == b'_' || *byte == b'-');
    if valid {
        return Ok(());
    }
    Err(ComputeLogError::rejected(
        ComputeLogErrorKind::InvalidCaptureId,
        "invocation_id must contain only ASCII letters, digits, underscores, or hyphens",
    ))
}

/// Python's `\d{4}-\d{2}-\d{2}\Z` date directory name.
pub(crate) fn is_capture_date(name: &str) -> bool {
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

/// The final component of `path` as text.
pub(crate) fn file_name(path: &Path) -> String {
    path.file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default()
}

/// `_ensure_not_symlink`.
pub(crate) fn ensure_not_symlink(path: &Path) -> Result<(), ComputeLogError> {
    if is_symlink(path) {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::Path,
            format!("compute log path cannot be a symlink: {}", path.display()),
        ));
    }
    Ok(())
}

/// `Path.resolve(strict=False)`: the deepest existing ancestor resolved, the rest appended.
fn resolve_lenient(path: &Path) -> PathBuf {
    let mut missing: Vec<std::ffi::OsString> = Vec::new();
    let mut existing: &Path = path;
    loop {
        if let Ok(resolved) = std::fs::canonicalize(existing) {
            return missing
                .iter()
                .rev()
                .fold(resolved, |resolved, name| resolved.join(name));
        }
        match (existing.parent(), existing.file_name()) {
            (Some(parent), Some(name)) => {
                missing.push(name.to_owned());
                existing = parent;
            }
            _ => return path.to_path_buf(),
        }
    }
}

/// `_ensure_contained`: `path` resolves beneath the configured `root`.
pub(crate) fn ensure_contained(root: &Path, path: &Path) -> Result<(), ComputeLogError> {
    if resolve_lenient(path).starts_with(root) {
        return Ok(());
    }
    Err(ComputeLogError::rejected(
        ComputeLogErrorKind::Path,
        format!(
            "compute log path escapes configured root: {}",
            path.display()
        ),
    ))
}

/// `_find_capture`: the one capture directory named `invocation_id` under any date directory.
pub(crate) fn find_capture(
    root: &Path,
    invocation_id: &str,
) -> Result<Option<PathBuf>, ComputeLogError> {
    validate_capture_id(invocation_id)?;
    let mut matches: Vec<PathBuf> = Vec::new();
    for entry in std::fs::read_dir(root)? {
        let date_directory = entry?.path();
        if !is_capture_date(&file_name(&date_directory)) {
            continue;
        }
        ensure_not_symlink(&date_directory)?;
        ensure_contained(root, &date_directory)?;
        if !date_directory.is_dir() {
            continue;
        }
        let candidate = date_directory.join(invocation_id);
        ensure_not_symlink(&candidate)?;
        if candidate.exists() {
            ensure_contained(root, &candidate)?;
            matches.push(candidate);
        }
    }
    if matches.len() > 1 {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::Metadata,
            format!("duplicate capture identity '{invocation_id}'"),
        ));
    }
    Ok(matches.pop())
}

/// `_find_capture` without `missing_ok`.
pub(crate) fn existing_capture(
    root: &Path,
    invocation_id: &str,
) -> Result<PathBuf, ComputeLogError> {
    find_capture(root, invocation_id)?.ok_or_else(|| {
        ComputeLogError::rejected(
            ComputeLogErrorKind::NotFound,
            format!("capture not found for invocation '{invocation_id}'"),
        )
    })
}

/// A read's nonnegative cursor and its byte limit, positive and no greater than the maximum.
pub(crate) fn read_bounds(cursor: i64, max_bytes: i64) -> Result<(u64, u64), ComputeLogError> {
    let cursor = u64::try_from(cursor).map_err(|_| {
        ComputeLogError::rejected(
            ComputeLogErrorKind::InvalidCursor,
            "cursor must be a nonnegative integer",
        )
    })?;
    let limit_error = || {
        ComputeLogError::rejected(
            ComputeLogErrorKind::InvalidLimit,
            format!("max_bytes must be a positive integer no greater than {MAX_READ_BYTES}"),
        )
    };
    let limit = u64::try_from(max_bytes).map_err(|_| limit_error())?;
    if !(1..=MAX_READ_BYTES).contains(&limit) {
        return Err(limit_error());
    }
    Ok((cursor, limit))
}
