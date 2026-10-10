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
pub(crate) const DESCRIPTION_KEY: &str = "description";
/// Config keys whose handling still runs in the Python attachment steps.
pub(crate) const CALLBACK_CONFIG_KEYS: [&str; 2] = ["pre_hooks", "post_hooks"];
/// Macro calls start with this token; SQL without it has nothing to expand.
pub(crate) const MACRO_TOKEN: char = '@';
