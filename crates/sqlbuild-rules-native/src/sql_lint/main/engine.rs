use crate::sql_lint::_helpers::engine::{lint_json_impl, rule_metadata};
use crate::sql_lint::models::LintRuleMetadata;

pub(crate) fn lint_json(request_json: &str) -> Result<String, String> {
    lint_json_impl(request_json)
}

pub(crate) fn catalogue() -> Vec<LintRuleMetadata> {
    rule_metadata()
}
