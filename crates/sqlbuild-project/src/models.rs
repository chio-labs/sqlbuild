//! The plain records the compiled project keeps for its resources.

use std::sync::Arc;

use sqlbuild_sqltext::compiler::models::CharSpan;

/// One reference a resource's SQL makes: kind, name, package and call argument count.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReferenceRow {
    pub kind: String,
    pub name: String,
    pub package: Option<String>,
    pub call_argument_count: Option<usize>,
}

/// A compiled relation location's parts.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DestinationFact {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub name: String,
    pub qualified_name: Option<String>,
    pub logical_schema: Option<String>,
    pub logical_database: Option<String>,
}

/// A model's name, compiled query, authored file, and whether it calls a function.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModelMetadataTexts {
    pub name: String,
    pub query_sql: String,
    pub authored_sql: String,
    pub calls_functions: bool,
}

/// The expansion passes of a model's query, from authored text to expanded SQL.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExpansionRecord {
    /// The authored query below the header.
    pub authored_sql: Arc<str>,
    /// The declaration- and macro-expanded SQL before canonicalisation.
    pub expanded_sql: Arc<str>,
    pub interpolation_spans: Vec<CharSpan>,
    pub declaration_spans: Vec<CharSpan>,
    pub macro_spans: Vec<CharSpan>,
    /// Whether interpolation left the authored query unchanged.
    pub authored: bool,
}
