//! The plain records the compiled project keeps for its resources.

use std::sync::Arc;

use sqlbuild_sqltext::compiler::models::CharSpan;

use sqlbuild_analysis::assembly::analysis_session::models::{ContractProof, LineageFacts};
use sqlbuild_analysis::binding_locations::models::LocatedDiagnostic;

use crate::types::{InferredRow, ProjectHost};

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

/// A model's attached header schema; the host keeps its columns, audits and dynamic columns.
#[derive(Debug)]
pub struct SchemaRecord<H: ProjectHost> {
    pub description: Option<String>,
    pub type_enforcement: bool,
    pub model_schema: Option<String>,
    pub host: H::Schema,
}

/// What the model loop finished for one model beyond its facts; the host keeps its user values.
#[derive(Debug)]
pub struct ModelInputRecord<H: ProjectHost> {
    /// The model's name, its file stem.
    pub name: String,
    /// Immutable text shared with discovery and expansions.
    pub query_sql: Arc<str>,
    pub macro_source_sql: Arc<str>,
    pub references: Vec<ReferenceRow>,
    pub schema: Option<SchemaRecord<H>>,
    pub sql_validation_enabled: bool,
    pub macro_deps: Vec<String>,
    pub expansion: ExpansionRecord,
    /// What assembly and the semantic checks finished, once the model is assembled.
    pub compiled: Option<CompiledRecord<H>>,
    pub host: H::ModelInput,
}

/// What one model's analysis left for its compiled model.
#[derive(Debug)]
pub struct AnalysisRecord<H: ProjectHost> {
    pub inferred: Option<Vec<InferredRow>>,
    pub lineage: Option<LineageFacts>,
    pub has_star: bool,
    pub star_resolved: bool,
    pub binding: Vec<LocatedDiagnostic>,
    pub binding_validated: bool,
    pub proof: Option<ContractProof>,
    pub host: H::Analysis,
}

/// What assembly and the semantic checks finished for one compiled model.
#[derive(Debug)]
pub struct CompiledRecord<H: ProjectHost> {
    /// `(resource type, name)` of each dependency.
    pub deps: Vec<(String, String)>,
    pub destination: DestinationFact,
    /// Columns, lineage, binding diagnostics and dynamic proof kept from the native session.
    pub analysis: AnalysisRecord<H>,
    pub macro_deps: Vec<String>,
    pub host: H::CompiledModel,
}
