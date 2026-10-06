pub(crate) fn analyze_json(request_json: &str) -> Result<String, String> {
    crate::column_references::references::analyze_json(request_json)
}
