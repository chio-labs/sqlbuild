pub(crate) fn finalize_findings_json(request_json: &str) -> Result<String, String> {
    crate::engine::_helpers::evaluation::finalize_findings_json(request_json)
}
