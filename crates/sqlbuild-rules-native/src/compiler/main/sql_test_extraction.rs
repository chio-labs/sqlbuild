use crate::compiler::_helpers;

pub(crate) fn extract_batch_json(request_json: &str) -> Result<String, String> {
    _helpers::sql_tests::extraction::extract_batch_json(request_json)
}
