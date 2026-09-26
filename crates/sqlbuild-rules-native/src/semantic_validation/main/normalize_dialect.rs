pub(crate) fn normalize_dialect_sql(sql: &str, dialect: &str) -> Result<String, String> {
    crate::semantic_validation::_helpers::normalization::normalize_dialect_sql(sql, dialect)
}
