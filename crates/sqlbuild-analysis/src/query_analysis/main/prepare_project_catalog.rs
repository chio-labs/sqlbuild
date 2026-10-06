pub(crate) fn prepare_project_compact_with_catalog(
    request_json: &str,
    catalog: &crate::semantic_validation::models::ProjectCatalog,
) -> Result<crate::semantic_validation::types::PreparedCompactAnalysis, String> {
    crate::query_analysis::engine::prepare_project_compact_with_catalog(request_json, catalog)
}
