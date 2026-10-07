//! Expected-model relationship names of SQL tests and scenarios, or a deferral to Python.

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::relationship_names::_helpers::cte_scan::{Deferred, expected_names};
use crate::relationship_names::models::ExpectedNames;

/// Return each SQL text's `__expected__<model>` names in CTE order, or a deferral to Python.
pub fn expected_model_names(sqls: &[String], syntax: &LexicalSyntax) -> Vec<ExpectedNames> {
    sqls.iter()
        .map(|sql| match expected_names(sql.as_bytes(), syntax) {
            Ok(names) => ExpectedNames::Scanned(names),
            Err(Deferred) => ExpectedNames::Deferred,
        })
        .collect()
}
