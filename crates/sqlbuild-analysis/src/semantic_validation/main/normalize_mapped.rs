use crate::semantic_validation::models::MappedNormalization;

/// The dialect normalization analysis applies to `sql`, mapped back to its input characters.
pub fn normalize_mapped(sql: &str, dialect: &str) -> Result<MappedNormalization, String> {
    crate::semantic_validation::_helpers::normalization::normalize_dialect_sql_mapped(sql, dialect)
        .map(|(sql, offsets)| MappedNormalization { sql, offsets })
}
