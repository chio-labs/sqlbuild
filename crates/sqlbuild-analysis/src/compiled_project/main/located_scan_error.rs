use sqlbuild_sqltext::sql_references::models::ReferenceScanFailure;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiled_project::models::ScanFaultOrigin;

/// The message a model's reference-scan fault raises, located in authored text when it can be.
pub fn located_scan_error(
    failure: &ReferenceScanFailure,
    sql: &str,
    origin: &ScanFaultOrigin<'_>,
    syntax: &LexicalSyntax,
) -> String {
    crate::compiled_project::_helpers::locating::located_scan_error(failure, sql, origin, syntax)
}
