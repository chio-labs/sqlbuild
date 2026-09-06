use crate::sql_lint::_helpers::formatter::format_json_impl;

pub(crate) fn format_json(request_json: &str) -> Result<String, String> {
    format_json_impl(request_json)
}
