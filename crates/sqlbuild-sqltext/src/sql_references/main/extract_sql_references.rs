//! Logical SQL references under one adapter's lexical rules.

use crate::sql_references::_helpers::scan::scan_references;
use crate::sql_references::models::{ReferenceExtraction, ReferenceScanFailure};
use crate::sql_scan::models::LexicalSyntax;

/// Return the references and rejected calls in `sql`, or the error that stops the scan.
pub fn extract_sql_references(sql: &str, syntax: &LexicalSyntax) -> ReferenceExtraction {
    match scan_references(sql, syntax) {
        Ok(scan) => ReferenceExtraction::Extracted(scan),
        Err((message, start)) => ReferenceExtraction::Failed(ReferenceScanFailure {
            message,
            start: sql[..start].chars().count(),
        }),
    }
}
