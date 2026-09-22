pub(crate) fn analyze_json(request_json: &str) -> Result<String, String> {
    crate::query_analysis::engine::analyze_json(request_json)
}
