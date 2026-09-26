use std::collections::HashMap;

pub(crate) fn normalize_analysis_sqls(
    dialect: &str,
    requests: Vec<(String, HashMap<String, String>)>,
) -> Result<Vec<String>, String> {
    let mut results: Vec<String> = Vec::with_capacity(requests.len());
    for (sql, placeholders) in requests {
        results.push(
            crate::semantic_validation::_helpers::normalization::normalize_analysis_sql(
                &sql,
                dialect,
                HashMap::new(),
                placeholders,
            )?,
        );
    }
    Ok(results)
}
