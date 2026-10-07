//! Building and splitting declaration scan errors.

use crate::declarations::errors::ScanError;
use crate::models::{DiscoveryFailure, FailureKind, StageFailure};
use crate::tree::main::display_text::display_text;
use std::borrow::Cow;

/// A listed relative path as a failure message shows it; message text is never decoded.
pub(crate) fn shown(relative_path: &str) -> Cow<'_, str> {
    display_text(relative_path)
}

/// The listed relative paths `paths`, shown and joined as Python lists them.
pub(crate) fn shown_list(paths: &[String]) -> String {
    paths
        .iter()
        .map(|path| shown(path))
        .collect::<Vec<Cow<'_, str>>>()
        .join(", ")
}

/// A `DeclarationParseError` with Python's message.
pub(crate) fn declaration_failure(message: String) -> ScanError {
    ScanError::Failure(DiscoveryFailure::new(FailureKind::Declaration, message))
}

/// Split a scan result into the authored outcome, keeping a stage failure for the caller.
pub(crate) fn authored_outcome<T>(
    result: Result<T, ScanError>,
) -> Result<Result<T, DiscoveryFailure>, StageFailure> {
    match result {
        Ok(value) => Ok(Ok(value)),
        Err(ScanError::Failure(failure)) => Ok(Err(failure)),
        Err(ScanError::Stage(failure)) => Err(failure),
    }
}
