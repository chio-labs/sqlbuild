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
/// Header metadata the native loop attaches itself.
pub(crate) const NATIVE_HEADER_KEYS: [&str; 3] = ["description", "columns", "audits"];
/// Macro calls start with this token; SQL without it has nothing to expand.
pub(crate) const MACRO_TOKEN: char = '@';
