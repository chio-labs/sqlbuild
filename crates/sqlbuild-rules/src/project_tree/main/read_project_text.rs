//! The text of a tracked project file as `Path.read_text(encoding="utf-8")` reads it.

use std::path::{Path, PathBuf};
use std::str::Utf8Error;

use crate::project_tree::_helpers::project_tree_file::project_tree_file;
use crate::project_tree::constants::{LINE_FEED, UTF8_INVALID_START};
use crate::project_tree::errors::{ProjectTextError, Utf8Failure, Utf8Reason};

/// The file's UTF-8 text with universal newlines, or why it cannot be read.
pub fn read_project_text(root: &Path, path: &Path) -> Result<String, ProjectTextError> {
    let file: PathBuf = project_tree_file(root, path).map_err(ProjectTextError::File)?;
    let bytes: Vec<u8> = match std::fs::read(&file) {
        Ok(bytes) => bytes,
        Err(error) => {
            return Err(ProjectTextError::Read {
                path: file,
                errno: error.raw_os_error().unwrap_or_default(),
            });
        }
    };
    match String::from_utf8(bytes) {
        Ok(text) => Ok(universal_newlines(&text)),
        Err(error) => Err(ProjectTextError::Decode(utf8_failure(
            error.as_bytes(),
            error.utf8_error(),
        ))),
    }
}

/// `\r\n` and lone `\r` as `\n`, as text mode reads them.
fn universal_newlines(text: &str) -> String {
    if !text.contains('\r') {
        return text.to_owned();
    }
    text.replace("\r\n", LINE_FEED).replace('\r', LINE_FEED)
}

/// The byte range and reason Python's strict UTF-8 decoder reports for `error`.
fn utf8_failure(bytes: &[u8], error: Utf8Error) -> Utf8Failure {
    let start: usize = error.valid_up_to();
    let first: u8 = bytes[start];
    match error.error_len() {
        None => Utf8Failure {
            byte: first,
            start,
            end: bytes.len(),
            reason: Utf8Reason::UnexpectedEnd,
        },
        Some(length) => Utf8Failure {
            byte: first,
            start,
            end: start + length,
            reason: if UTF8_INVALID_START
                .iter()
                .any(|range| range.contains(&first))
            {
                Utf8Reason::InvalidStart
            } else {
                Utf8Reason::InvalidContinuation
            },
        },
    }
}
