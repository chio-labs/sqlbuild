//! Native results for SQL model files.

use crate::models::LineColumnSpan;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

/// What the Python facade asked for, with the header key sets Python owns during dual running.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModelFileOptions {
    pub supported_keys: Vec<String>,
    pub removed_keys: Vec<String>,
    pub extract_implicit_alias_columns: bool,
    pub extract_output_column_locations: bool,
    /// The string semantics of the Python whose discovery output native must reproduce.
    pub python: PythonText,
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
