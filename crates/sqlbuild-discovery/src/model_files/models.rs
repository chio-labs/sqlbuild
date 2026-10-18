//! Native results for SQL model files.

use crate::models::LineColumnSpan;
use sqlbuild_model_config::config_presence::models::MacroPath;
use sqlbuild_model_config::header_metadata::models::ParsedThresholds;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

/// What the Python facade asked for, with the header key sets Python owns during dual running.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModelFileOptions {
    pub supported_keys: Vec<String>,
    pub removed_keys: Vec<String>,
    pub extract_implicit_alias_columns: bool,
    pub extract_output_column_locations: bool,
    /// Discover only these project-relative paths, when given.
    pub path_filter: Option<std::sync::Arc<std::collections::BTreeSet<String>>>,
}

/// One parsed model file; values mirror the fields of Python's `DiscoveredSqlModelFile`.
#[derive(Clone, Debug, PartialEq)]
pub struct DiscoveredModelFile {
    pub contents: String,
    pub header_values: Vec<(String, AuthoredValue)>,
    pub header_column_locations: Vec<(String, LineColumnSpan)>,
    /// In Python's assignment order; a repeated name keeps its first position and last value.
    pub output_column_locations: Vec<(String, LineColumnSpan)>,
    pub query_sql: String,
}

/// What one top-level header entry holds, as the config checks walk it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EntryFacts {
    /// Whether a string in the value holds a `${...}` template.
    pub template: bool,
    /// Where the config macro walk finds a macro call in this entry.
    pub macro_path: MacroPath,
    /// Whether the value keeps the model from reusing another model's config.
    pub blocks_reuse: bool,
}

/// One model's header facts, read from its native authored values.
#[derive(Clone, Debug, PartialEq)]
pub struct HeaderFacts {
    /// Each header key in the projected dict's order, with its facts.
    pub entries: Vec<(String, EntryFacts)>,
    /// The header's columns, when they parse exactly and without an error.
    pub columns: Option<Vec<NativeColumn>>,
}

impl HeaderFacts {
    /// The facts of `key`'s value in the header.
    #[must_use]
    pub fn entry(&self, key: &str) -> Option<&EntryFacts> {
        self.entries
            .iter()
            .find(|(name, _)| name == key)
            .map(|(_, facts)| facts)
    }
}

/// One MODEL column parsed from native authored values.
#[derive(Clone, Debug, PartialEq)]
pub struct NativeColumn {
    pub name: String,
    pub column_type: Option<String>,
    pub nullable: Option<bool>,
    pub description: Option<String>,
    pub audits: Vec<NativeAudit>,
    pub migrate_from: Option<String>,
}

/// One audit instance parsed from native authored values.
#[derive(Clone, Debug, PartialEq)]
pub struct NativeAudit {
    pub definition_name: String,
    pub arguments: Vec<(String, AuthoredValue)>,
    pub name: Option<String>,
    pub description: Option<String>,
    pub severity: Option<String>,
    pub run_scope: Option<String>,
    pub always_run: Option<bool>,
    pub thresholds: Option<ParsedThresholds>,
    pub minimum_samples: Option<AuthoredValue>,
    pub evidence_limit: Option<AuthoredValue>,
    pub meta: Option<AuthoredValue>,
}
