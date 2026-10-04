use crate::sql_lint::models::LintDiagnostic;
use crate::sql_quality::constants::{
    LONG_LITERAL, RANKING_SORT_CAP, REPEATED_JSON_PARSE, UNSTABLE_ROW_NUMBER_CODE,
    UNUSED_CTE_OUTPUT,
};
use crate::sql_quality::keys::{KeyEnvironment, key_environment};
use crate::sql_quality::models::QualityRequest;
use crate::sql_quality::{cte_columns, json_parses, literals, ranking};

/// Run every enabled SQL quality Rule over one parsed body.
pub(crate) fn diagnostics(request: &QualityRequest<'_>) -> Result<Vec<LintDiagnostic>, String> {
    if request.max_literal_length == 0 || request.max_ranking_order_by == 0 {
        return Err("max_literal_length and max_ranking_order_by must be positive".to_owned());
    }
    let mut found: Vec<LintDiagnostic> = Vec::new();
    if request.enabled.contains(LONG_LITERAL.code) {
        found.extend(literals::diagnostics(request));
    }
    if request.enabled.contains(REPEATED_JSON_PARSE.code) {
        found.extend(json_parses::diagnostics(request));
    }
    if request.enabled.contains(UNUSED_CTE_OUTPUT.code) {
        found.extend(cte_columns::diagnostics(request));
    }
    if request.enabled.contains(RANKING_SORT_CAP.code)
        || request.enabled.contains(UNSTABLE_ROW_NUMBER_CODE)
    {
        let environment: KeyEnvironment = key_environment(request);
        found.extend(ranking::diagnostics(request, &environment));
    }
    Ok(found)
}
