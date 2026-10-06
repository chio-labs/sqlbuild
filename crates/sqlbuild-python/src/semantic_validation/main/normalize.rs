use crate::semantic_validation::models::NormalizationInput;

pub(crate) fn normalize_analysis_sql(request: NormalizationInput) -> Result<String, String> {
    crate::semantic_validation::_helpers::normalization::normalize_analysis_sql(
        &request.sql,
        &request.dialect,
        request.stubs,
        request.placeholders,
    )
}
