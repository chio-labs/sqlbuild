//! Building and splitting declaration scan errors.

use crate::declarations::errors::ScanError;
use crate::models::{DiscoveryFailure, FailureKind, StageFailure};

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
