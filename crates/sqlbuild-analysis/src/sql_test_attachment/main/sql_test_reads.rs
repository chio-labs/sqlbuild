//! The `sql_test_reads` helper check of the compile attachment.

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::sql_test_attachment::_helpers::attachment_checks;
use crate::sql_test_attachment::models::{ModelTestCtes, SqlTestCheckFailure, SqlTestReadFacts};
use crate::sql_test_attachment::types::SqlTestTextMatcher;

/// `sql_test_reads`: the helpers a test reads and the unmocked models they read.
pub fn sql_test_reads<M: SqlTestTextMatcher>(
    payload: &ModelTestCtes<'_>,
    syntax: &LexicalSyntax,
    matcher: &M,
) -> Result<SqlTestReadFacts, SqlTestCheckFailure<M::Error>> {
    attachment_checks::sql_test_reads(payload, syntax, matcher)
}
