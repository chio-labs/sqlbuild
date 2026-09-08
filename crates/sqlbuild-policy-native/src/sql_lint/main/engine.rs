use crate::sql_lint::_helpers::engine::lint_json_impl;

pub(crate) fn lint_json(request_json: &str) -> Result<String, String> {
    lint_json_impl(request_json)
}
