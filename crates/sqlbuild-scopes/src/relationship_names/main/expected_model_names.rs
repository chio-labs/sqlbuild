//! Expected-model relationship names of SQL tests and scenarios, Python's error, or a deferral.

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::relationship_names::_helpers::cte_scan::{ScanText, Stop, expected_names};
use crate::relationship_names::models::{ExpectedNames, RelationshipSource};

/// Return each `(sql, file label)` text's expected-model names, Python's error, or a deferral.
pub fn expected_model_names(
    texts: &[(String, String)],
    source: RelationshipSource,
    syntax: &LexicalSyntax,
) -> Vec<ExpectedNames> {
    texts
        .iter()
        .map(
            |(sql, file)| match expected_names(&ScanText { sql, file, source }, syntax) {
                Ok(names) => ExpectedNames::Scanned(names),
                Err(Stop::Failed(message)) => ExpectedNames::Failed(message),
                Err(Stop::Deferred) => ExpectedNames::Deferred,
            },
        )
        .collect()
}
