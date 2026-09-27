pub(crate) fn analyze_project_compact_with_catalog(
    request_json: &str,
    catalog: &crate::semantic_validation::models::ProjectCatalog,
) -> Result<String, String> {
    crate::query_analysis::engine::analyze_project_compact_with_catalog(request_json, Some(catalog))
}
