use crate::query_facts::models::ModelShape;

/// A model's SQL with dependency calls stubbed by occurrence, mapped back to its characters.
pub(crate) fn model_shape(sql: &str, dialect: &str) -> Result<ModelShape, String> {
    crate::query_facts::_helpers::shape::model_shape(sql, dialect)
}
