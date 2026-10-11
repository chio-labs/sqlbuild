//! Reference kinds audit validation reads and the cross-resource audit threshold.

pub(crate) const REF_KIND: &str = "ref";
pub(crate) const SEED_KIND: &str = "seed";
pub(crate) const SOURCE_KIND: &str = "source";
pub(crate) const DBT_REF_KIND: &str = "dbt_ref";
pub(crate) const TABLE_FUNCTION_KIND: &str = "table_fn";
pub(crate) const MODEL_RESOURCE: &str = "model";
pub(crate) const SOURCE_RESOURCE: &str = "source";
pub(crate) const SEED_RESOURCE: &str = "seed";
pub(crate) const FUNCTION_RESOURCE: &str = "function";
/// Singular audits reading fewer models must also read a companion resource.
pub(crate) const CROSS_MODEL_MINIMUM: usize = 2;
/// The run scope Python falls back to without an instance or project value.
pub(crate) const FALLBACK_RUN_SCOPE: &str = "delta_and_final";
