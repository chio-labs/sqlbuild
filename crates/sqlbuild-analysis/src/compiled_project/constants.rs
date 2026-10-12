//! Config keys and SQL tokens the native model loop reads, as the Python attachment names them.

/// Header keys attached as schema metadata and stripped from the model's config.
pub(crate) const HEADER_METADATA_KEYS: [&str; 8] = [
    "description",
    "columns",
    "dynamic_columns",
    "model_schema",
    "audits",
    "audit_factories",
    "enums",
    "constants",
];
pub(crate) const DECLARATION_EXPANSION_CONTEXT: &str = "Enum and constant expansion";
pub(crate) const UNCLOSED_BLOCK_COMMENT_STOP: u8 = 1;
pub(crate) const INVALID_ENUM_REFERENCE_STOP: u8 = 2;
pub(crate) const INVALID_CONSTANT_REFERENCE_STOP: u8 = 3;
/// Macro calls start with this token; SQL without it has nothing to expand.
pub(crate) const MACRO_TOKEN: char = '@';
/// The keys whose `false` value opts a model out of SQL analysis.
pub(crate) const OPT_OUT_KEYS: [&str; 2] = ["sql_analysis", "sql_validation"];
pub(crate) const NEWLINE: char = '\n';
