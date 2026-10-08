//! The invalid-header-syntax failure every statement header reports, as Python's discovery does.

use crate::models::{DiscoveryFailure, FailureKind};
use sqlbuild_sqltext::compiler::main::model_header_errors::header_nesting_failure;

/// One header that failed to parse, with the one-based file line its text starts on.
pub(crate) struct FailedHeader<'a> {
    pub(crate) kind: FailureKind,
    /// The name in syntax errors, such as `MODEL`.
    pub(crate) statement_name: &'a str,
    pub(crate) file_path: &'a str,
    pub(crate) text: &'a str,
    pub(crate) line: usize,
}

/// The invalid-syntax failure for `error`; a nesting error names its file line and a fix.
pub(crate) fn header_syntax_failure(header: &FailedHeader<'_>, error: &str) -> DiscoveryFailure {
    let (statement_name, file_path) = (header.statement_name, header.file_path);
    let Some(nesting) = header_nesting_failure(error, header.text, header.line) else {
        return DiscoveryFailure::new(
            header.kind,
            format!(
                "{statement_name}(...) in '{file_path}' contains invalid SQLBuild header syntax: \
                 {error}"
            ),
        );
    };
    DiscoveryFailure {
        kind: header.kind,
        message: format!(
            "{statement_name}(...) in '{file_path}:{}' contains invalid SQLBuild header syntax: {}",
            nesting.line, nesting.message
        ),
        help: Some(nesting.help),
    }
}
