//! Plain-data request, deferrals and outcomes of the native model analysis session.

use std::collections::HashMap;

use crate::assembly::analysis_session::_helpers::catalog_state::SessionCatalog;
use crate::assembly::analysis_session::_helpers::mappings::ShapeTable;
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::semantic_validation::types::DiagnosticRow;

/// One `ref`, `source`, `seed`, `table_fn` or `udf` call a model's SQL makes.
#[derive(Debug, Clone)]
pub struct ModelReference {
    /// Python's `_analysis_reference_name`.
    pub analysis_name: String,
    /// Whether the call is a `ref`, so names a model the analysis orders by.
    pub model_ref: bool,
}

/// One analysed model, with the facts Python derives from its compile input.
#[derive(Debug, Clone)]
pub struct ModelRequest {
    pub name: String,
    /// Cursor-intrinsic analysis SQL.
    pub query_sql: String,
    pub placeholders: Pairs,
    pub references: Vec<ModelReference>,
    /// Python's `lineage_reference_map`: `(analysis name, resource type, resource name)`.
    pub lineage_references: Vec<(String, String, String)>,
    /// Sorted `binding_relation_names`.
    pub required_names: Vec<String>,
    pub recover_cte_facts: bool,
    /// Whether the SQL names `UNION`, `INTERSECT` or `EXCEPT`, as Python's search decides it.
    pub has_set_operation: bool,
    /// The snapshot validity columns a published shape appends.
    pub snapshot_columns: Option<(String, String)>,
    /// The SQL Python's dynamic pivot proof parses: placeholders replaced by their defaults.
    pub pivot_sql: String,
    pub dynamic_families: Vec<DynamicFamily>,
}

/// One declared family of columns a runtime-dynamic pivot generates.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DynamicFamily {
    pub name: String,
    pub pivot_column: String,
    pub value_column: String,
    pub aggregate: String,
    pub data_type: String,
    pub name_pattern: Option<String>,
}

/// Python's `DynamicColumnContractProof`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractProof {
    pub output_proven: bool,
    pub fixed_columns: Vec<ColumnFact>,
    /// Each family's name and inferred type.
    pub families: Vec<(String, Option<String>)>,
    pub input_relations: Vec<String>,
    pub failure_reason: Option<String>,
    pub bare_dynamic_pivot: bool,
}

/// One model's dynamic pivot proof inputs, for a model the session does not analyse.
#[derive(Debug, Clone, Default)]
pub struct PivotRequest {
    pub dialect: String,
    pub column_types: Shapes,
    pub authoritative_types: Shapes,
    pub column_nullability: Shapes,
    pub families_by_table: Vec<(String, Vec<DynamicFamily>)>,
    pub sql: String,
    pub families: Vec<DynamicFamily>,
}

/// A model's dynamic pivot proof: none declared, left to Python, or proven natively.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PivotOutcome {
    Absent,
    Deferred,
    Proof(ContractProof),
}

/// Everything one compile's model analysis reads.
#[derive(Debug, Clone, Default)]
pub struct SessionRequest {
    /// The analysis dialect, `generic` when the adapter names none.
    pub dialect: String,
    /// Whether published shapes keep authored quoting, Python's `inferred_binding_shape` test.
    pub case_sensitive_shapes: bool,
    pub function_return_types: Pairs,
    /// Adapter nullability rules as `(function name, rule id)`; None where one is not Python's.
    pub nullability_rules: Option<Pairs>,
    pub rich_type_inference: bool,
    pub column_types: Shapes,
    pub column_nullability: Shapes,
    pub complete_schemas: Shapes,
    /// The Python binding catalog's `schemas` before analysis.
    pub catalog_schemas: Shapes,
    /// Python's `dynamic_families_by_table`, in dict order.
    pub dynamic_families_by_table: Vec<(String, Vec<DynamicFamily>)>,
    pub models: Vec<ModelRequest>,
}

/// One inferred output column; nullability is Python's `InferredNullability` value.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ColumnFact {
    pub name: String,
    pub data_type: Option<String>,
    pub nullability: String,
}

/// One compact lineage row with resolved names; codes index Python's enum tuples.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LineageRow {
    pub output_column: String,
    pub transform_code: u8,
    pub confidence_code: u8,
    pub sources: Vec<(String, String, String)>,
}

/// Where a model's lineage facts live.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LineageFacts {
    /// Native compact rows.
    Native(Vec<LineageRow>),
    /// The lineage of the analysis Python returned for this model's analysis deferral.
    PythonAnalysis,
    /// The lineage of the analysis Python returned for this model's enrichment deferral.
    PythonEnrichment,
    /// Plain lineage facts of a native re-analysis or legacy analysis.
    NativeFacts(Vec<LineageRow>),
}

/// Python's `PolyglotAnalysisResult` for one model.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelAnalysis {
    pub analysis_succeeded: bool,
    pub columns: Option<Vec<ColumnFact>>,
    pub lineage: LineageFacts,
    pub has_star: bool,
    pub star_resolved: bool,
    pub binding_diagnostics: Vec<DiagnosticRow>,
    pub binding_validated: bool,
}

/// Python's `ModelSqlAnalysis` for one model, without the placeholders Python keeps.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelOutcome {
    pub analysis: ModelAnalysis,
    pub cleaned_sql: String,
    pub validated_schema: Shapes,
    pub fused_binding_validated: bool,
}

/// Work native analysis hands back to Python for one model.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Deferral {
    /// The native engine asked for Python's legacy analysis of this model.
    Analysis {
        model: usize,
        cleaned_sql: String,
        binding_schema: Shapes,
        binding_diagnostics: Vec<DiagnosticRow>,
        /// Lineage Python projects from native rows, when the engine kept them.
        lineage: Option<Vec<LineageRow>>,
    },
    /// Re-analysis with the model's known input shapes.
    Enrichment { model: usize, input_schemas: Shapes },
}

/// Python's answer to one deferral, without the lineage Python keeps.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeferredAnalysis {
    pub model: usize,
    pub analysis_succeeded: bool,
    pub columns: Option<Vec<ColumnFact>>,
    pub has_star: bool,
    pub star_resolved: bool,
    pub binding_diagnostics: Vec<DiagnosticRow>,
    pub binding_validated: bool,
}

/// One phase of the session: the deferrals Python must answer, or none when it is done.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SessionStep {
    /// Shapes published since the previous step, in publication order.
    pub publications: Shapes,
    pub deferrals: Vec<Deferral>,
    /// Native analysis failures Python logs at debug level.
    pub failures: Vec<String>,
}

/// The session's results once every deferral is answered.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SessionOutcome {
    pub models: Vec<ModelOutcome>,
    /// Relations the Python binding catalog adds to `schemas`, in order.
    pub schema_additions: Shapes,
    /// Relations whose analysis shapes the Python binding catalog records.
    pub analysis_names: Vec<String>,
    /// Each model's dynamic pivot proof, in request order.
    pub dynamic_contracts: Vec<PivotOutcome>,
}

/// One expression source's shape: inferred, absent, or left to Python.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExpressionShape {
    Inferred(Pairs),
    Absent,
    Deferred,
}

/// What expression-source shape inference reads from the inference profile.
#[derive(Debug, Clone, Default)]
pub struct ExpressionShapeRequest {
    pub dialect: String,
    pub case_sensitive_shapes: bool,
    pub function_return_types: Pairs,
    pub expressions: Vec<String>,
}

/// Deferrals the session waits on before it continues a wave.
#[derive(Debug)]
pub(crate) enum Awaiting {
    Analyses {
        wave: usize,
        models: Vec<usize>,
    },
    Enrichments {
        wave: usize,
        star_pending: HashMap<usize, bool>,
    },
}

/// Where the session is within its waves.
#[derive(Debug)]
pub(crate) enum Phase {
    Analyze,
    Complete(usize),
    Finish(usize),
    Await(Awaiting),
    Done,
}

/// One compile's model analysis, advanced phase by phase and resumed with Python's answers.
#[derive(Debug)]
pub struct AnalysisSession {
    pub(crate) request: SessionRequest,
    pub(crate) catalog: SessionCatalog,
    pub(crate) dependency_ordered: bool,
    pub(crate) waves: Vec<Vec<usize>>,
    pub(crate) next_wave: usize,
    pub(crate) available_types: ShapeTable,
    pub(crate) available_nullability: ShapeTable,
    pub(crate) complete_shapes: ShapeTable,
    pub(crate) outcomes: Vec<Option<ModelOutcome>>,
    pub(crate) phase: Phase,
    pub(crate) publications: Shapes,
    pub(crate) failures: Vec<String>,
}

/// One query's CTE fact recovery, as Python's compact enrichment runs it.
#[derive(Debug, Clone)]
pub struct CteFactRequest {
    pub cleaned_sql: String,
    pub dialect: String,
    /// Input relation types; every input column's nullability is unknown, as in enrichment.
    pub input_schemas: Shapes,
    pub function_return_types: Pairs,
    /// Adapter nullability rules as `(function name, rule id)`; None where one is not Python's.
    pub nullability_rules: Option<Pairs>,
    /// Whether Python runs `_polyglot_cte_passthrough_facts` past its early return.
    pub recover: bool,
    /// Whether a filter reads NULL, so Python looks for filtered non-null outputs.
    pub null_filter: bool,
}

/// Python's recovered CTE pass-through facts and filtered non-null outputs for one query.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CteFacts {
    pub types: Pairs,
    pub nullability: Pairs,
    /// Sorted direct CTE output names.
    pub direct_outputs: Vec<String>,
    /// Sorted outputs a filter proves non-null.
    pub non_null_outputs: Vec<String>,
}
