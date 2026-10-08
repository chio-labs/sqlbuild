//! Logical SQL references under one adapter's lexical rules, or a deferral to Python.

use crate::sql_references::_helpers::scan::{Stopped, scan_references};
use crate::sql_references::constants::SUPPORTED_LINE_COMMENT_PREFIXES;
use crate::sql_references::models::{ReferenceExtraction, ReferenceScanFailure};
use crate::sql_scan::models::LexicalSyntax;

/// Return the references and rejected calls Python finds in `sql`, or its error message.
pub fn extract_sql_references(sql: &str, syntax: &LexicalSyntax) -> ReferenceExtraction {
    if !syntax
        .line_comment_prefixes
        .iter()
        .all(|prefix| SUPPORTED_LINE_COMMENT_PREFIXES.contains(&prefix.as_str()))
    {
        return ReferenceExtraction::Deferred;
    }
    match scan_references(sql.as_bytes(), syntax) {
        Ok(scan) => ReferenceExtraction::Extracted(scan),
        Err(Stopped::Failed(message, start)) => {
            sql.get(..start)
                .map_or(ReferenceExtraction::Deferred, |prefix| {
                    ReferenceExtraction::Failed(ReferenceScanFailure {
                        message,
                        start: prefix.chars().count(),
                    })
                })
        }
        Err(Stopped::Deferred) => ReferenceExtraction::Deferred,
    }
}
