//! The `unresolvable_test_references` helper check of the compile attachment.

use std::collections::HashSet;

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::sql_test_attachment::_helpers::attachment_checks;
use crate::sql_test_attachment::models::{
    ModelTestCtes, SqlTestCheckFailure, SqlTestHelperProblem,
};
use crate::sql_test_attachment::types::SqlTestTextMatcher;

/// `report_unresolvable_test_references`: each P013 problem, in Python's report order.
pub fn unresolvable_test_references<M: SqlTestTextMatcher>(
    payload: &ModelTestCtes<'_>,
    known_models: &HashSet<String>,
    syntax: &LexicalSyntax,
    matcher: &M,
) -> Result<Vec<SqlTestHelperProblem>, SqlTestCheckFailure<M::Error>> {
    attachment_checks::unresolvable_test_references(payload, known_models, syntax, matcher)
}
