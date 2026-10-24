//! The invalid-header-syntax failure every statement header reports, as Python's discovery does.

use crate::models::{DiscoveryFailure, FailureKind};
use sqlbuild_sqltext::compiler::main::model_header_errors::header_nesting_failure;
use sqlbuild_sqltext::header_strings::main::quote_failure::quote_failure;

/// One header that failed to parse, with the one-based file line its text starts on.
pub(crate) struct FailedHeader<'a> {
    pub(crate) kind: FailureKind,
    /// The name in syntax errors, such as `MODEL`.
    pub(crate) statement_name: &'a str,
    pub(crate) file_path: &'a str,
    pub(crate) text: &'a str,
    pub(crate) line: usize,
    /// The one-based column of the header text's first character.
    pub(crate) column: usize,
}

/// The one-based line and column of byte offset `start` in `contents`.
pub(crate) fn header_position(contents: &str, start: usize) -> (usize, usize) {
    let before: &str = &contents[..start];
    let line_start: usize = before.rfind('\n').map_or(0, |newline| newline + 1);
    (
        before.matches('\n').count() + 1,
        before[line_start..].chars().count() + 1,
    )
}

/// The invalid-syntax failure for `error`; a nesting error names its file line and a fix.
pub(crate) fn header_syntax_failure(header: &FailedHeader<'_>, error: &str) -> DiscoveryFailure {
    let (statement_name, file_path) = (header.statement_name, header.file_path);
    if let Some(quote) = quote_failure(error, header.text, (header.line, header.column)) {
        return DiscoveryFailure {
            kind: header.kind,
            message: format!(
                "{statement_name}(...) in '{file_path}:{}:{}' contains invalid SQLBuild header \
                 syntax: {}",
                quote.line, quote.column, quote.message
            ),
            help: Some(quote.help),
        };
    }
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
