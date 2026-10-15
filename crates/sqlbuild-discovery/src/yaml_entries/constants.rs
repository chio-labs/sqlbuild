//! The top-level keys of source and schema YAML documents and integration loader kinds.

/// The keys a schema YAML file under `seeds/` may declare.
pub(crate) const SEED_FILE_KEYS: [&str; 1] = ["seeds"];
/// The keys a sources YAML file may declare.
pub(crate) const SOURCE_FILE_KEYS: [&str; 2] = ["sources", "dlt_sources"];

/// The integration kind whose loaders run under the bare source name.
pub(crate) const DLT_LOADER_KIND: &str = "dlt";
