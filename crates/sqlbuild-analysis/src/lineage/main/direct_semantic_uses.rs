//! Direct semantic lineage uses over native model and schema facts.

use crate::lineage::models::{DirectSemanticUse, RichSchemaResource};

/// Resolve semantic uses to project resources and authored character positions.
pub fn direct_semantic_uses(
    schema: &[RichSchemaResource],
    models: &[(String, String, String)],
    dialect: &str,
) -> Result<Vec<DirectSemanticUse>, String> {
    crate::lineage::_helpers::semantic_uses::direct_semantic_uses(schema, models, dialect)
}
