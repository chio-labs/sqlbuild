//! SQL tests classified natively, as the compile attachment reads them.

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiler::_helpers;
use crate::compiler::models::{SqlTestClassification, SqlTestExtractionFailure, SqlTestRequest};

/// Each test's classification, or the first test's failure, under the adapter's lexical rules.
pub fn extract_sql_tests(
    tests: &[SqlTestRequest],
    syntax: &LexicalSyntax,
) -> Result<Vec<SqlTestClassification>, SqlTestExtractionFailure> {
    _helpers::sql_tests::extraction::extract_tests(tests, syntax).map_err(|(index, failure)| {
        SqlTestExtractionFailure {
            index,
            message: failure.message,
            help: failure.help,
            token: failure.token,
        }
    })
}
