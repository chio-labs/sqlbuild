use crate::models::{Model, ModelRow, ModelRowsContext};

/// Build each model's rules facts and type proofs from its compiled-model row.
pub fn build_models(
    rows: Vec<ModelRow>,
    context: ModelRowsContext<'_>,
    fallback: impl FnMut(&str, &str) -> Result<bool, String>,
) -> Result<Vec<Model>, String> {
    crate::engine::_helpers::rows::build_models(rows, context, fallback)
}
