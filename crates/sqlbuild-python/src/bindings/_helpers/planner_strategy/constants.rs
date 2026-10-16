//! Audit plan boundary modules and attachment values.

pub(crate) const AUDIT_TYPES_MODULE: &str = "sqlbuild.compiler.auditing.types";
pub(crate) const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
pub(crate) const MODEL_ATTACHMENT: &str = "model";
pub(crate) const SOURCE_ATTACHMENT: &str = "source";
pub(crate) const INCREMENTAL_MATERIALIZATION: &str = "incremental";
pub(crate) const MICROBATCH_MODE: &str = "microbatch";
pub(crate) const CUSTOM_MATERIALIZATION: &str = "custom";
pub(crate) const ENFORCED_CONTRACT: &str = "enforced";
pub(crate) const TIMESTAMP_CURSOR: &str = "timestamp";
pub(crate) const MODEL_REFERENCE: &str = "ref";
pub(crate) const SEED_REFERENCE: &str = "seed";
pub(crate) const SOURCE_REFERENCE: &str = "source";
pub(crate) const DDL_SEPARATOR: &str = ";\n\n";
/// The lineage confidence whose reads fixtures must provide.
pub(crate) const HIGH_CONFIDENCE: &str = "high";
/// The lineage transform kind that passes an input column's type through.
pub(crate) const DIRECT_TRANSFORM: &str = "direct";
/// Resource type values keying fixture relations.
pub(crate) const MODEL_REFERENCE_KIND: &str = "model";
pub(crate) const SOURCE_REFERENCE_KIND: &str = "source";
pub(crate) const SEED_REFERENCE_KIND: &str = "seed";
