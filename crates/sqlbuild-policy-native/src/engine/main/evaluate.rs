pub(crate) fn evaluate_json(request_json: &str) -> Result<String, String> {
    crate::engine::_helpers::evaluation::evaluate_json(request_json)
}
