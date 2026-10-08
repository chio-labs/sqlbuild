//! Polyglot expression kinds and SQLBuild reference spellings read by fast lineage.

pub(crate) const STAR_COLUMN_NAME: &str = "*";
pub(crate) const KIND_ALIAS: &str = "alias";
pub(crate) const KIND_COLUMN: &str = "column";
pub(crate) const KIND_SELECT: &str = "select";
pub(crate) const KIND_TABLE: &str = "table";
pub(crate) const KIND_UNION: &str = "union";
pub(crate) const SET_OPERATION_KINDS: &[&str] = &["union", "intersect", "except"];
pub(crate) const CAST_KINDS: &[&str] = &["cast", "try_cast"];
pub(crate) const AGGREGATE_KINDS: &[&str] = &[
    "avg",
    "count",
    "max",
    "min",
    "sum",
    "array_agg",
    "string_agg",
];
pub(crate) const PAYLOAD_COLUMN: &str = "column";
pub(crate) const PAYLOAD_NAME: &str = "name";
pub(crate) const PAYLOAD_TABLE: &str = "table";
pub(crate) const SET_OPERATION_SIDES: [&str; 2] = ["left", "right"];
/// The function-call depth SQLBuild's Polyglot proxy passes on every parse.
pub(crate) const MAX_FUNCTION_CALL_DEPTH: usize = 512;
pub(crate) const REFERENCE_PREFIX: &str = "__";
pub(crate) const UDF_CALL: &str = "__udf(";
pub(crate) const PHYSICAL_RESOURCE_PREFIX: &str = "__sqlbuild_";
pub(crate) const PHYSICAL_NAME_REPLACEMENT: &str = "__";
