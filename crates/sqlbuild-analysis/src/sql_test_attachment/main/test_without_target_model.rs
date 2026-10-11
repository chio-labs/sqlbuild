//! The `test_without_target_model` helper check of the compile attachment.

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::sql_test_attachment::_helpers::attachment_checks;
use crate::sql_test_attachment::models::{
    ModelTestCtes, SqlTestCheckFailure, SqlTestHelperProblem,
};
use crate::sql_test_attachment::types::SqlTestTextMatcher;

/// `report_test_without_target_model`: the P013 problem of a test that runs no model.
pub fn test_without_target_model<M: SqlTestTextMatcher>(
    payload: &ModelTestCtes<'_>,
    test_name: &str,
    syntax: &LexicalSyntax,
    matcher: &M,
) -> Result<SqlTestHelperProblem, SqlTestCheckFailure<M::Error>> {
    attachment_checks::test_without_target_model(payload, test_name, syntax, matcher)
}
