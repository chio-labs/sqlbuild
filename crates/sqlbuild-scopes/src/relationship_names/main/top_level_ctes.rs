//! Top-level CTEs of SQL tests and scenarios as Python's scanner reads them.

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::relationship_names::_helpers::cte_scan::{ScanText, top_level_ctes};
use crate::relationship_names::models::{RelationshipSource, TopLevelCtes};

/// Return the top-level CTEs of one SQL text, or the error the scanner raises.
pub fn scan_top_level_ctes(
    sql: &str,
    file: &str,
    source: RelationshipSource,
    syntax: &LexicalSyntax,
) -> TopLevelCtes {
    match top_level_ctes(&ScanText { sql, file, source }, syntax) {
        Ok(ctes) => TopLevelCtes::Scanned(ctes),
        Err(message) => TopLevelCtes::Failed(message),
    }
}
