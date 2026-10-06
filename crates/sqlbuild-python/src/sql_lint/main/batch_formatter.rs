use crate::sql_lint::_helpers::formatter::format_batch_json_impl;

pub(crate) fn format_batch_json(request_json: &str) -> Result<String, String> {
    format_batch_json_impl(request_json)
}
